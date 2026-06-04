"""LLMProvider implementation that calls the Anthropic Messages API."""

import json
import logging
import os
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

from schmidt.llm.max_tokens import resolve_max_tokens
from schmidt.llm.provider import LLMMessage, LLMProvider, SamplingParams, T

logger = logging.getLogger(__name__)

ANTHROPIC_RETRY_ATTEMPTS = 3
STRUCTURED_OUTPUT_ATTEMPTS = 2


def _log_structured_retry(retry_state: RetryCallState) -> None:
    """Log a warning when a structured output attempt fails before retrying."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "Structured output attempt %d failed, retrying: %s",
        retry_state.attempt_number,
        exc,
    )


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
    # anthropic SDK messages.create is overloaded on `stream`; **kwargs hides
    # the literal from pyright. We always call with stream=False.
    client_any: Any = client
    response: anthropic.types.Message = await client_any.messages.create(**kwargs)
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
        sampling: SamplingParams | None = None,
    ) -> T:
        """Call the Claude API with a forced tool call and return a validated Pydantic model.

        Converts the output_schema into an Anthropic tool definition,
        forces the model to call it via tool_choice, and validates the
        response arguments against the schema. Retries on validation
        failures (e.g. missing fields, stringified arrays) with a fresh
        API call. When ``sampling`` is provided its temperature is forwarded;
        otherwise the model's default sampling applies.
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
            "max_tokens": resolve_max_tokens(),
            "system": system_with_cache,
            "messages": anthropic_messages,
            "tools": [tool_def],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        if sampling is not None:
            kwargs["temperature"] = sampling.temperature

        @retry(
            retry=retry_if_exception_type((ValidationError, ValueError)),
            stop=stop_after_attempt(STRUCTURED_OUTPUT_ATTEMPTS),
            wait=wait_fixed(0),
            reraise=True,
            before_sleep=_log_structured_retry,
        )
        async def _call_and_validate() -> T:
            response = await _create_with_retry(client=self._client, kwargs=kwargs)

            self._record_usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
                cache_creation_input_tokens=getattr(
                    response.usage, "cache_creation_input_tokens", 0
                ),
            )

            arguments: dict[str, Any] | None = None
            for block in response.content:
                if block.type == "tool_use" and block.name == tool_name:
                    arguments = dict(block.input)
                    break

            if arguments is None:
                raise ValueError(f"LLM response did not contain a {tool_name} tool call")

            repaired = _repair_stringified_fields(
                arguments=arguments,
                schema_cls=output_schema,
            )
            return output_schema.model_validate(repaired)

        return await _call_and_validate()


def _repair_stringified_fields(
    arguments: dict[str, Any],
    schema_cls: type[BaseModel],
) -> dict[str, Any]:
    """Attempt to JSON-parse string values where the schema expects a list or object.

    Smaller models sometimes return stringified arrays or objects in tool call
    responses. This pre-validation pass detects those cases using the Pydantic
    JSON schema and coerces them back to their intended types.
    """
    schema = schema_cls.model_json_schema()
    properties = schema.get("properties", {})
    repaired = dict(arguments)
    for field_name, field_schema in properties.items():
        value = repaired.get(field_name)
        if not isinstance(value, str):
            continue
        expected_type = field_schema.get("type")
        if expected_type not in ("array", "object"):
            continue
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            continue
        if expected_type == "array" and isinstance(parsed, list):
            repaired[field_name] = parsed
            logger.debug("Repaired stringified %s field: %s", expected_type, field_name)
        elif expected_type == "object" and isinstance(parsed, dict):
            repaired[field_name] = parsed
            logger.debug("Repaired stringified %s field: %s", expected_type, field_name)
    return repaired


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
