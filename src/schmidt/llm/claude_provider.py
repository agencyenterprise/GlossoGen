"""LLMProvider implementation that calls the Anthropic Messages API."""

import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

import anthropic
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from schmidt.llm.provider import LLMMessage, LLMProvider, LLMResponse, T
from schmidt.models.event import TokenUsage
from schmidt.models.tool_definition import ToolCallRequest, ToolSpec

logger = logging.getLogger(__name__)

ANTHROPIC_RETRY_ATTEMPTS = 3


def _is_retryable_api_error(exc: BaseException) -> bool:
    """Return True for rate-limit (429) and server (5xx) errors from the Anthropic API."""
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return True
    return False


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    stop=stop_after_attempt(ANTHROPIC_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True,
)
async def _create_with_retry(
    client: anthropic.AsyncAnthropic,
    kwargs: dict[str, Any],
) -> anthropic.types.Message:
    """Call the Anthropic Messages API with exponential-backoff retry on transient errors."""
    response: anthropic.types.Message = await client.messages.create(**kwargs)
    return response


class ClaudeProvider(LLMProvider):
    """LLMProvider backed by the Anthropic Claude Messages API.

    Reads the ANTHROPIC_API_KEY from the environment and uses the async
    Anthropic client to send chat-completion requests. The system prompt
    is sent with ephemeral cache control.
    """

    def __init__(self, model: str) -> None:
        """Initialize the provider with the given model identifier.

        Raises RuntimeError if ANTHROPIC_API_KEY is not set in the environment.
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        logger.info("ClaudeProvider initialized with model=%s", model)

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        tools: list[ToolSpec],
        force_tool_use: bool,
        max_tokens: int,
    ) -> LLMResponse:
        """Send a message sequence to the Claude API and return the parsed response.

        Converts the provided tool specs and messages into the Anthropic API
        format, calls the Messages endpoint, and extracts text blocks, tool-use
        blocks, and token usage from the response.
        """
        anthropic_tools = [_convert_tool_spec(spec=spec) for spec in tools]
        anthropic_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        system_with_cache: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system_with_cache,
            "messages": anthropic_messages,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
            if force_tool_use:
                kwargs["tool_choice"] = {"type": "any"}

        logger.debug(
            "Calling Claude API: model=%s, messages=%d, tools=%d",
            self._model,
            len(anthropic_messages),
            len(anthropic_tools),
        )
        response = await _create_with_retry(client=self._client, kwargs=kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        raw_content: list[dict[str, Any]] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
                raw_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                if isinstance(block.input, dict):
                    arguments = block.input
                else:
                    arguments = {}
                tool_calls.append(
                    ToolCallRequest(
                        call_id=block.id,
                        tool_name=block.name,
                        arguments=arguments,
                    )
                )
                raw_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": arguments,
                    }
                )

        raw_cache_read = getattr(response.usage, "cache_read_input_tokens", None)
        raw_cache_create = getattr(response.usage, "cache_creation_input_tokens", None)

        if raw_cache_read is not None:
            cache_read = raw_cache_read
        else:
            cache_read = 0
        if raw_cache_create is not None:
            cache_create = raw_cache_create
        else:
            cache_create = 0

        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_create,
        )

        logger.debug(
            "Claude API response: stop_reason=%s, tool_calls=%d, "
            "input_tokens=%d, output_tokens=%d, cache_read=%d, cache_create=%d",
            response.stop_reason,
            len(tool_calls),
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_input_tokens,
            usage.cache_creation_input_tokens,
        )

        if text_parts:
            text = "\n".join(text_parts)
        else:
            text = None
        if response.stop_reason is not None:
            stop_reason = response.stop_reason
        else:
            stop_reason = "end_turn"

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
        """Call the Claude API with a forced tool call and return a validated Pydantic model.

        Converts the output_schema into an Anthropic tool definition,
        forces the model to call it via tool_choice, and validates the
        response arguments against the schema.
        """
        tool_name = output_schema.__name__
        tool_def = _schema_to_tool(schema_cls=output_schema, tool_name=tool_name)

        anthropic_messages = [{"role": msg.role, "content": msg.content} for msg in messages]
        system_with_cache: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "system": system_with_cache,
            "messages": anthropic_messages,
            "tools": [tool_def],
            "tool_choice": {"type": "tool", "name": tool_name},
        }

        logger.debug(
            "Calling Claude API (structured): model=%s, schema=%s",
            self._model,
            tool_name,
        )
        response = await _create_with_retry(client=self._client, kwargs=kwargs)

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                if isinstance(block.input, dict):
                    arguments = block.input
                else:
                    arguments = {}
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
        """Stream a Claude API response, calling on_token for each text delta.

        Uses the Anthropic streaming API to deliver text chunks in real time.
        Tool-use blocks are accumulated and returned in the final LLMResponse.
        Calls ``on_tool_arg_delta`` for each tool argument JSON fragment.
        Retries only apply to the initial connection, not mid-stream failures.
        """
        anthropic_tools = [_convert_tool_spec(spec=spec) for spec in tools]
        anthropic_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        system_with_cache: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system_with_cache,
            "messages": anthropic_messages,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
            if force_tool_use:
                kwargs["tool_choice"] = {"type": "any"}

        logger.debug(
            "Calling Claude API (streaming): model=%s, messages=%d, tools=%d",
            self._model,
            len(anthropic_messages),
            len(anthropic_tools),
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        raw_content: list[dict[str, Any]] = []

        # Track in-progress tool_use blocks by index
        tool_use_builders: dict[int, dict[str, Any]] = {}

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        tool_use_builders[event.index] = {
                            "id": block.id,
                            "name": block.name,
                            "input_json": "",
                        }
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        text_parts.append(delta.text)
                        await on_token(delta.text)
                    elif delta.type == "input_json_delta":
                        builder = tool_use_builders.get(event.index)
                        if builder is not None:
                            builder["input_json"] += delta.partial_json
                            await on_tool_arg_delta(
                                event.index,
                                builder["name"],
                                delta.partial_json,
                                builder["input_json"],
                            )

            final_message = await stream.get_final_message()

        # Build raw_content and tool_calls from the final message
        for block in final_message.content:
            if block.type == "text":
                raw_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                if isinstance(block.input, dict):
                    arguments = block.input
                else:
                    arguments = {}
                tool_calls.append(
                    ToolCallRequest(
                        call_id=block.id,
                        tool_name=block.name,
                        arguments=arguments,
                    )
                )
                raw_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": arguments,
                    }
                )

        raw_cache_read = getattr(final_message.usage, "cache_read_input_tokens", None)
        raw_cache_create = getattr(final_message.usage, "cache_creation_input_tokens", None)

        if raw_cache_read is not None:
            cache_read = raw_cache_read
        else:
            cache_read = 0
        if raw_cache_create is not None:
            cache_create = raw_cache_create
        else:
            cache_create = 0

        usage = TokenUsage(
            input_tokens=final_message.usage.input_tokens,
            output_tokens=final_message.usage.output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_create,
        )

        logger.debug(
            "Claude API streaming response: stop_reason=%s, tool_calls=%d, "
            "input_tokens=%d, output_tokens=%d",
            final_message.stop_reason,
            len(tool_calls),
            usage.input_tokens,
            usage.output_tokens,
        )

        if text_parts:
            text = "".join(text_parts)
        else:
            text = None
        if final_message.stop_reason is not None:
            stop_reason = final_message.stop_reason
        else:
            stop_reason = "end_turn"

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            raw_content=raw_content,
        )


def _schema_to_tool(schema_cls: type[BaseModel], tool_name: str) -> dict[str, Any]:
    """Convert a Pydantic model class into an Anthropic tool definition.

    Uses the model's JSON schema as the tool's input_schema. The model's
    docstring becomes the tool description; if no docstring exists, a
    default message is used instead.
    """
    json_schema = schema_cls.model_json_schema()
    description = schema_cls.__doc__
    if description is None:
        description = f"Submit structured output as {tool_name}."
    return {
        "name": tool_name,
        "description": description.strip(),
        "input_schema": json_schema,
    }


def _convert_tool_spec(spec: ToolSpec) -> dict[str, Any]:
    """Convert a ToolSpec into the Anthropic tool JSON schema format."""
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
        "name": spec.name,
        "description": spec.description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required_params,
        },
    }
