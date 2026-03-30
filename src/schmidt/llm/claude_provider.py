"""LLMProvider implementation that calls the Anthropic Messages API."""

import logging
import os
from typing import Any

import anthropic
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from schmidt.llm.provider import LLMMessage, LLMProvider, T

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
    Anthropic client for structured output via tool calling.
    """

    def __init__(self, model: str) -> None:
        """Initialize the provider with the given model identifier.

        Raises RuntimeError if ANTHROPIC_API_KEY is not set in the environment.
        """
        super().__init__()
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        logger.info("ClaudeProvider initialized with model=%s", model)

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

        self._record_usage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
            cache_creation_input_tokens=getattr(response.usage, "cache_creation_input_tokens", 0),
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                if isinstance(block.input, dict):
                    arguments = block.input
                else:
                    arguments = {}
                return output_schema.model_validate(arguments)

        raise ValueError(f"LLM response did not contain a {tool_name} tool call")


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
