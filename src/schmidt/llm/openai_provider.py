"""LLMProvider implementation that calls the OpenAI Responses API."""

import json
import logging
import os
from typing import Any

import openai
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from schmidt.llm.provider import LLMMessage, LLMProvider, T

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
    OpenAI client for structured output via function calling.
    """

    def __init__(self, model: str, reasoning_effort: str | None) -> None:
        """Initialize the provider with the given model identifier.

        Raises RuntimeError if OPENAI_API_KEY is not set in the environment.
        """
        super().__init__()
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

        if response.usage is not None:
            cached = 0
            if hasattr(response.usage, "input_tokens_details"):
                details = response.usage.input_tokens_details
                if details is not None and hasattr(details, "cached_tokens"):
                    cached = details.cached_tokens
            self._record_usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_read_input_tokens=cached,
                cache_creation_input_tokens=0,
            )

        for item in response.output:
            if item.type == "function_call" and item.name == tool_name:
                try:
                    arguments = json.loads(item.arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                return output_schema.model_validate(arguments)

        raise ValueError(f"LLM response did not contain a {tool_name} function call")


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
