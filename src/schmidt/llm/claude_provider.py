"""LLMProvider implementation that calls the Anthropic Messages API."""

import logging
import os
from typing import Any

import anthropic
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from schmidt.llm.provider import LLMMessage, LLMProvider, LLMResponse
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
            "max_tokens": 4096,
            "system": system_with_cache,
            "messages": anthropic_messages,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

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
                tool_calls.append(
                    ToolCallRequest(
                        call_id=block.id,
                        tool_name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )
                raw_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input if isinstance(block.input, dict) else {},
                    }
                )

        raw_cache_read = getattr(response.usage, "cache_read_input_tokens", None)
        raw_cache_create = getattr(response.usage, "cache_creation_input_tokens", None)

        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=raw_cache_read if raw_cache_read is not None else 0,
            cache_creation_input_tokens=raw_cache_create if raw_cache_create is not None else 0,
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

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason if response.stop_reason is not None else "end_turn",
            usage=usage,
            raw_content=raw_content,
        )


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
