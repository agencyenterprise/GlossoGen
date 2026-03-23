"""LLMProvider implementation that calls the OpenAI Responses API."""

import json
import logging
import os
from typing import Any

import openai
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from schmidt.llm.provider import LLMMessage, LLMProvider, LLMResponse, T
from schmidt.models.event import TokenUsage
from schmidt.models.tool_definition import ToolCallRequest, ToolSpec

logger = logging.getLogger(__name__)

OPENAI_RETRY_ATTEMPTS = 3


def _is_retryable_api_error(exc: BaseException) -> bool:
    """Return True for rate-limit and server errors from the OpenAI API."""
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return True
    return False


@retry(
    retry=retry_if_exception(_is_retryable_api_error),
    stop=stop_after_attempt(OPENAI_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True,
)
async def _responses_with_retry(
    client: openai.AsyncOpenAI,
    kwargs: dict[str, Any],
) -> Any:
    """Call the OpenAI Responses API with exponential-backoff retry."""
    response = await client.responses.create(**kwargs)
    return response


class OpenAIProvider(LLMProvider):
    """LLMProvider backed by the OpenAI Responses API.

    Reads the OPENAI_API_KEY from the environment and uses the async
    OpenAI client to send response requests. Supports reasoning effort
    configuration for reasoning-capable models.
    """

    def __init__(self, model: str, reasoning_effort: str | None) -> None:
        """Initialize the provider with the given model identifier.

        Raises RuntimeError if OPENAI_API_KEY is not set in the environment.
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set")
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._reasoning_effort = reasoning_effort
        logger.info(
            "OpenAIProvider initialized with model=%s, reasoning_effort=%s",
            model,
            reasoning_effort,
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        tools: list[ToolSpec],
        force_tool_use: bool,
    ) -> LLMResponse:
        """Send a message sequence to the OpenAI Responses API and return the parsed response.

        Translates Anthropic-style content blocks (tool_use, tool_result) into
        the Responses API input format before sending.
        """
        input_items = _build_responses_input(messages=messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "instructions": system_prompt,
            "input": input_items,
            "store": False,
        }

        if self._reasoning_effort is not None:
            kwargs["reasoning"] = {"effort": self._reasoning_effort}

        if tools:
            kwargs["tools"] = [_convert_tool_spec_to_responses(spec=spec) for spec in tools]
            if force_tool_use:
                kwargs["tool_choice"] = "required"

        logger.debug(
            "Calling OpenAI Responses API: model=%s, input_items=%d, tools=%d",
            self._model,
            len(input_items),
            len(tools),
        )
        response = await _responses_with_retry(client=self._client, kwargs=kwargs)

        return _parse_responses_output(response=response)

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[T],
    ) -> T:
        """Call the Responses API with function calling, return a validated Pydantic model."""
        tool_name = output_schema.__name__
        tool_def = _schema_to_responses_tool(schema_cls=output_schema, tool_name=tool_name)

        input_items: list[dict[str, Any]] = []
        for msg in messages:
            input_items.append({"role": msg.role, "content": msg.content})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "instructions": system_prompt,
            "input": input_items,
            "tools": [tool_def],
            "tool_choice": {"type": "function", "name": tool_name},
            "store": False,
        }

        if self._reasoning_effort is not None:
            kwargs["reasoning"] = {"effort": self._reasoning_effort}

        logger.debug(
            "Calling OpenAI Responses API (structured): model=%s, schema=%s",
            self._model,
            tool_name,
        )
        response = await _responses_with_retry(client=self._client, kwargs=kwargs)

        for item in response.output:
            if item.type == "function_call" and item.name == tool_name:
                try:
                    arguments = json.loads(item.arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                return output_schema.model_validate(arguments)

        raise ValueError(f"LLM response did not contain a {tool_name} function call")


def _parse_responses_output(response: Any) -> LLMResponse:
    """Parse an OpenAI Responses API response into an LLMResponse."""
    text: str | None = None
    tool_calls: list[ToolCallRequest] = []
    raw_content: list[dict[str, Any]] = []
    stop_reason = "stop"

    for item in response.output:
        if item.type == "message":
            for content_block in item.content:
                if content_block.type == "output_text":
                    text = content_block.text
                    raw_content.append({"type": "text", "text": text})
        elif item.type == "function_call":
            try:
                arguments = json.loads(item.arguments)
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            tool_calls.append(
                ToolCallRequest(
                    call_id=item.call_id,
                    tool_name=item.name,
                    arguments=arguments,
                )
            )
            raw_content.append(
                {
                    "type": "tool_use",
                    "id": item.call_id,
                    "name": item.name,
                    "input": arguments,
                }
            )
            stop_reason = "tool_use"

    usage_data = response.usage
    if usage_data is not None:
        input_tokens = usage_data.input_tokens
        output_tokens = usage_data.output_tokens
    else:
        input_tokens = 0
        output_tokens = 0

    usage = TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )

    logger.debug(
        "OpenAI Responses API response: stop_reason=%s, tool_calls=%d, "
        "input_tokens=%d, output_tokens=%d",
        stop_reason,
        len(tool_calls),
        input_tokens,
        output_tokens,
    )

    return LLMResponse(
        text=text,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        usage=usage,
        raw_content=raw_content,
    )


def _build_responses_input(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """Convert Anthropic-style messages into Responses API input items.

    Handles three cases per message:
    - Plain text content: converted to a simple ``{role, content}`` message.
    - Assistant content with tool_use blocks: split into a text message (if any)
      followed by ``function_call`` input items.
    - User content with tool_result blocks: converted to ``function_call_output``
      input items.
    """
    items: list[dict[str, Any]] = []

    for msg in messages:
        converted = _convert_message_to_responses(role=msg.role, content=msg.content)
        items.extend(converted)

    return items


def _convert_message_to_responses(
    role: str,
    content: str | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert a single Anthropic-style message into Responses API input items."""
    if isinstance(content, str):
        return [{"role": role, "content": content}]

    if role == "assistant":
        result: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for block in content:
            if block.get("type") == "text":
                text_parts.append(block["text"])
            elif block.get("type") == "tool_use":
                result.append(
                    {
                        "type": "function_call",
                        "call_id": block["id"],
                        "name": block["name"],
                        "arguments": json.dumps(block.get("input", {})),
                    }
                )
        if text_parts:
            result.insert(0, {"role": "assistant", "content": "\n".join(text_parts)})
        return result

    if role == "user":
        has_tool_results = any(block.get("type") == "tool_result" for block in content)
        if has_tool_results:
            result_items: list[dict[str, Any]] = []
            for block in content:
                if block.get("type") == "tool_result":
                    result_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": block["tool_use_id"],
                            "output": str(block.get("content", "")),
                        }
                    )
            return result_items

        text_content = " ".join(str(block.get("text", "")) for block in content)
        return [{"role": "user", "content": text_content}]

    return [{"role": role, "content": str(content)}]


def _schema_to_responses_tool(schema_cls: type[BaseModel], tool_name: str) -> dict[str, Any]:
    """Convert a Pydantic model class into a Responses API function tool definition.

    Enables strict mode and adjusts the JSON schema to be compatible with OpenAI's
    structured output requirements (``additionalProperties: false`` at each level,
    ``$defs`` inlined).
    """
    json_schema = schema_cls.model_json_schema()
    _enforce_strict_schema(schema=json_schema)
    description = schema_cls.__doc__
    if description is None:
        description = f"Submit structured output as {tool_name}."
    return {
        "type": "function",
        "name": tool_name,
        "description": description.strip(),
        "parameters": json_schema,
        "strict": True,
    }


def _enforce_strict_schema(schema: dict[str, Any]) -> None:
    """Recursively add ``additionalProperties: false`` to all object-type schemas.

    OpenAI's strict mode requires this at every level. Also processes ``$defs``
    and nested ``items`` schemas.
    """
    if schema.get("type") == "object" and "properties" in schema:
        schema["additionalProperties"] = False
        for prop_schema in schema["properties"].values():
            _enforce_strict_schema(schema=prop_schema)

    if "items" in schema and isinstance(schema["items"], dict):
        _enforce_strict_schema(schema=schema["items"])

    if "$defs" in schema:
        for def_schema in schema["$defs"].values():
            _enforce_strict_schema(schema=def_schema)


def _convert_tool_spec_to_responses(spec: ToolSpec) -> dict[str, Any]:
    """Convert a ToolSpec into the Responses API function tool format."""
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
        "name": spec.name,
        "description": spec.description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required_params,
        },
    }
