"""LLMProvider implementation that calls the HuggingFace Serverless Inference API."""

import json
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.errors import HfHubHTTPError
from huggingface_hub.inference._generated.types.chat_completion import (
    ChatCompletionInputFunctionName,
    ChatCompletionInputToolChoiceClass,
    ChatCompletionOutput,
    ChatCompletionStreamOutput,
)
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from schmidt.llm.provider import LLMMessage, LLMProvider, LLMResponse, T
from schmidt.models.event import TokenUsage
from schmidt.models.tool_definition import ToolCallRequest, ToolSpec

logger = logging.getLogger(__name__)

HF_RETRY_ATTEMPTS = 3

_FINISH_REASON_MAP: dict[str, str] = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "length": "max_tokens",
    "eos_token": "end_turn",
}


def _is_retryable_hf_error(exc: BaseException) -> bool:
    """Return True for rate-limit (429) and server (5xx) errors from the HuggingFace API."""
    if not isinstance(exc, HfHubHTTPError):
        return False
    response = exc.response
    if response is None:
        return False
    if response.status_code == 429:
        return True
    if response.status_code >= 500:
        return True
    return False


@retry(
    retry=retry_if_exception(_is_retryable_hf_error),
    stop=stop_after_attempt(HF_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True,
)
async def _chat_completion_with_retry(
    client: AsyncInferenceClient,
    kwargs: dict[str, Any],
) -> ChatCompletionOutput:
    """Call the HuggingFace chat completion API with retry on transient errors."""
    response: ChatCompletionOutput = await client.chat_completion(**kwargs)
    return response


def _normalize_finish_reason(finish_reason: str) -> str:
    """Map OpenAI-style finish reasons to Anthropic-style stop reasons."""
    mapped = _FINISH_REASON_MAP.get(finish_reason)
    if mapped is not None:
        return mapped
    return finish_reason


def _convert_tool_spec_to_openai(spec: ToolSpec) -> dict[str, Any]:
    """Convert a ToolSpec into the OpenAI function-calling tool format."""
    properties: dict[str, Any] = {}
    required_params: list[str] = []

    for param in spec.parameters:
        properties[param.name] = {
            "type": param.param_type,
            "description": param.description,
        }
        if param.required:
            required_params.append(param.name)

    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required_params,
            },
        },
    }


def _schema_to_openai_tool(schema_cls: type[BaseModel], tool_name: str) -> dict[str, Any]:
    """Convert a Pydantic model class into an OpenAI function-calling tool definition."""
    json_schema = schema_cls.model_json_schema()
    description = schema_cls.__doc__
    if description is None:
        description = f"Submit structured output as {tool_name}."

    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": description.strip(),
            "parameters": json_schema,
        },
    }


def _convert_anthropic_assistant_content(
    content: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert an Anthropic-style assistant content block list to OpenAI format.

    Anthropic assistant messages use a list of typed blocks (text, tool_use).
    OpenAI expects a single content string plus a tool_calls array.
    """
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    for block in content:
        if block.get("type") == "text":
            text_parts.append(block["text"])
        elif block.get("type") == "tool_use":
            tool_calls.append(
                {
                    "role": "assistant",
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block.get("input", {})),
                    },
                }
            )

    msg: dict[str, Any] = {"role": "assistant"}
    if text_parts:
        msg["content"] = "\n".join(text_parts)
    else:
        msg["content"] = ""
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def _convert_anthropic_tool_results(
    content: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert Anthropic-style tool_result blocks to OpenAI tool-role messages.

    Anthropic sends tool results as a single user message with a list of
    tool_result blocks. OpenAI expects separate messages with role=tool.
    """
    tool_messages: list[dict[str, Any]] = []
    for block in content:
        if block.get("type") == "tool_result":
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": block["tool_use_id"],
                    "content": block.get("content", ""),
                }
            )
    return tool_messages


def _build_messages(
    system_prompt: str,
    messages: list[LLMMessage],
) -> list[dict[str, Any]]:
    """Build the OpenAI-format message list with the system prompt prepended.

    Handles conversion of Anthropic-style structured content blocks
    (tool_use, tool_result) into the OpenAI message format.
    """
    openai_messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    for msg in messages:
        if isinstance(msg.content, str):
            openai_messages.append({"role": msg.role, "content": msg.content})
            continue

        # Structured content blocks from the agent runner
        if msg.role == "assistant":
            openai_messages.append(_convert_anthropic_assistant_content(content=msg.content))
        elif msg.role == "user":
            # Check if this is a tool results message
            has_tool_results = any(
                isinstance(block, dict) and block.get("type") == "tool_result"
                for block in msg.content
            )
            if has_tool_results:
                openai_messages.extend(_convert_anthropic_tool_results(content=msg.content))
            else:
                openai_messages.append({"role": msg.role, "content": msg.content})
        else:
            openai_messages.append({"role": msg.role, "content": msg.content})

    return openai_messages


def _parse_tool_calls_from_message(
    tool_calls_raw: list[Any] | None,
) -> tuple[list[ToolCallRequest], list[dict[str, Any]]]:
    """Extract ToolCallRequests and raw content dicts from OpenAI-format tool calls."""
    tool_calls: list[ToolCallRequest] = []
    raw_content: list[dict[str, Any]] = []

    if tool_calls_raw is None:
        return tool_calls, raw_content

    for tc in tool_calls_raw:
        if tc.function.arguments:
            arguments = json.loads(tc.function.arguments)
        else:
            arguments = {}
        tool_calls.append(
            ToolCallRequest(
                call_id=tc.id,
                tool_name=tc.function.name,
                arguments=arguments,
            )
        )
        raw_content.append(
            {
                "type": "tool_use",
                "id": tc.id,
                "name": tc.function.name,
                "input": arguments,
            }
        )

    return tool_calls, raw_content


class HuggingFaceProvider(LLMProvider):
    """LLMProvider backed by the HuggingFace Inference API.

    Reads the HF_TOKEN from the environment and uses the async inference client
    to send chat-completion requests with OpenAI-compatible tool calling.
    Supports routing to third-party inference providers (Together AI, Fireworks,
    Cerebras, Groq, etc.) via the inference_provider parameter.
    """

    def __init__(self, model: str, inference_provider: str | None) -> None:
        """Initialize the provider with the given model and optional inference provider.

        Raises RuntimeError if HF_TOKEN is not set in the environment.
        """
        hf_token = os.environ.get("HF_TOKEN")
        if not hf_token:
            raise RuntimeError("HF_TOKEN environment variable is not set")
        self._client = AsyncInferenceClient(
            token=hf_token, model=model, provider=inference_provider  # type: ignore[arg-type]
        )
        self._model = model
        self._inference_provider = inference_provider
        logger.info(
            "HuggingFaceProvider initialized with model=%s, inference_provider=%s",
            model,
            inference_provider,
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        tools: list[ToolSpec],
        force_tool_use: bool,
        max_tokens: int,
    ) -> LLMResponse:
        """Send a message sequence to the HuggingFace API and return the parsed response.

        Converts the provided tool specs and messages into the OpenAI-compatible
        format, calls the chat completion endpoint, and extracts text, tool-use
        blocks, and token usage from the response.
        """
        openai_messages = _build_messages(system_prompt=system_prompt, messages=messages)
        openai_tools = [_convert_tool_spec_to_openai(spec=spec) for spec in tools]

        kwargs: dict[str, Any] = {
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
            if force_tool_use:
                kwargs["tool_choice"] = "required"

        logger.debug(
            "Calling HuggingFace API: model=%s, messages=%d, tools=%d",
            self._model,
            len(openai_messages),
            len(openai_tools),
        )
        response = await _chat_completion_with_retry(client=self._client, kwargs=kwargs)

        choice = response.choices[0]
        message = choice.message

        text = message.content
        tool_calls, tool_raw_content = _parse_tool_calls_from_message(
            tool_calls_raw=message.tool_calls,
        )

        raw_content: list[dict[str, Any]] = []
        if text is not None:
            raw_content.append({"type": "text", "text": text})
        raw_content.extend(tool_raw_content)

        usage = TokenUsage(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        stop_reason = _normalize_finish_reason(finish_reason=choice.finish_reason)

        logger.debug(
            "HuggingFace API response: stop_reason=%s, tool_calls=%d, "
            "input_tokens=%d, output_tokens=%d",
            stop_reason,
            len(tool_calls),
            usage.input_tokens,
            usage.output_tokens,
        )

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            raw_content=raw_content,
        )

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[T],
    ) -> T:
        """Call the HuggingFace API with a forced tool call and return a validated Pydantic model.

        Converts the output_schema into an OpenAI function tool definition,
        forces the model to call it via tool_choice, and validates the
        response arguments against the schema.
        """
        tool_name = output_schema.__name__
        tool_def = _schema_to_openai_tool(schema_cls=output_schema, tool_name=tool_name)

        openai_messages = _build_messages(system_prompt=system_prompt, messages=messages)

        kwargs: dict[str, Any] = {
            "messages": openai_messages,
            "max_tokens": 4096,
            "stream": False,
            "tools": [tool_def],
            "tool_choice": ChatCompletionInputToolChoiceClass(
                function=ChatCompletionInputFunctionName(name=tool_name),
            ),
        }

        logger.debug(
            "Calling HuggingFace API (structured): model=%s, schema=%s",
            self._model,
            tool_name,
        )
        response = await _chat_completion_with_retry(client=self._client, kwargs=kwargs)

        choice = response.choices[0]
        message = choice.message

        if message.tool_calls is not None:
            for tc in message.tool_calls:
                if tc.function.name == tool_name:
                    arguments = json.loads(tc.function.arguments)
                    return output_schema.model_validate(arguments)

        raise ValueError(f"LLM response did not contain a {tool_name} tool call")

    async def generate_streaming(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        tools: list[ToolSpec],
        force_tool_use: bool,
        max_tokens: int,
        on_token: Callable[[str], Awaitable[None]],
        on_tool_arg_delta: Callable[[int, str, str, str], Awaitable[None]],
    ) -> LLMResponse:
        """Stream a HuggingFace API response, calling on_token for each text delta.

        Uses the HuggingFace streaming API to deliver text chunks in real time.
        Tool-use blocks are accumulated and returned in the final LLMResponse.
        Calls ``on_tool_arg_delta`` for each tool argument JSON fragment.
        """
        openai_messages = _build_messages(system_prompt=system_prompt, messages=messages)
        openai_tools = [_convert_tool_spec_to_openai(spec=spec) for spec in tools]

        kwargs: dict[str, Any] = {
            "messages": openai_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
            if force_tool_use:
                kwargs["tool_choice"] = "required"

        logger.debug(
            "Calling HuggingFace API (streaming): model=%s, messages=%d, tools=%d",
            self._model,
            len(openai_messages),
            len(openai_tools),
        )

        text_parts: list[str] = []
        # Track in-progress tool calls by index: {index: {id, name, arguments_json}}
        tool_builders: dict[int, dict[str, str]] = {}
        finish_reason = "end_turn"
        input_tokens = 0
        output_tokens = 0

        stream: Any = await self._client.chat_completion(**kwargs)
        chunk: ChatCompletionStreamOutput
        async for chunk in stream:
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content is not None:
                text_parts.append(delta.content)
                await on_token(delta.content)

            if delta.tool_calls is not None:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_builders:
                        tool_builders[idx] = {
                            "id": tc_delta.id,
                            "name": tc_delta.function.name if tc_delta.function.name else "",
                            "arguments_json": "",
                        }
                    builder = tool_builders[idx]
                    arg_fragment = tc_delta.function.arguments
                    if arg_fragment:
                        builder["arguments_json"] += arg_fragment
                        await on_tool_arg_delta(
                            idx,
                            builder["name"],
                            arg_fragment,
                            builder["arguments_json"],
                        )

            if choice.finish_reason is not None:
                finish_reason = _normalize_finish_reason(
                    finish_reason=choice.finish_reason,
                )

            if chunk.usage is not None:
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens

        # Build final tool calls from accumulated builders
        tool_calls: list[ToolCallRequest] = []
        raw_content: list[dict[str, Any]] = []

        if text_parts:
            text = "".join(text_parts)
            raw_content.append({"type": "text", "text": text})
        else:
            text = None

        for builder in [tool_builders[k] for k in sorted(tool_builders)]:
            if builder["arguments_json"]:
                arguments = json.loads(builder["arguments_json"])
            else:
                arguments = {}
            tool_calls.append(
                ToolCallRequest(
                    call_id=builder["id"],
                    tool_name=builder["name"],
                    arguments=arguments,
                )
            )
            raw_content.append(
                {
                    "type": "tool_use",
                    "id": builder["id"],
                    "name": builder["name"],
                    "input": arguments,
                }
            )

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )

        logger.debug(
            "HuggingFace API streaming response: stop_reason=%s, tool_calls=%d, "
            "input_tokens=%d, output_tokens=%d",
            finish_reason,
            len(tool_calls),
            usage.input_tokens,
            usage.output_tokens,
        )

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=finish_reason,
            usage=usage,
            raw_content=raw_content,
        )
