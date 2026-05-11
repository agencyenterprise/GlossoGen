"""LLMProvider implementation that calls the HuggingFace Serverless Inference API."""

import json
import logging
import os
from typing import Any

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.errors import HfHubHTTPError
from huggingface_hub.inference._generated.types.chat_completion import (
    ChatCompletionInputFunctionName,
    ChatCompletionInputToolChoiceClass,
    ChatCompletionOutput,
)
from pydantic import BaseModel
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from schmidt.llm.max_tokens import resolve_max_tokens
from schmidt.llm.provider import LLMMessage, LLMProvider, T

logger = logging.getLogger(__name__)

HF_RETRY_ATTEMPTS = 3


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


class HuggingFaceProvider(LLMProvider):
    """LLMProvider backed by the HuggingFace Inference API.

    Reads the HF_TOKEN from the environment and uses the async inference client
    for structured output via OpenAI-compatible function calling.
    Supports routing to third-party inference providers (Together AI, Fireworks,
    Cerebras, Groq, etc.) via the inference_provider parameter.
    """

    def __init__(self, model: str, inference_provider: str | None) -> None:
        """Initialize the provider with the given model and optional inference provider.

        Raises RuntimeError if HF_TOKEN is not set in the environment.
        """
        super().__init__()
        hf_token = os.environ.get("HF_TOKEN")
        if not hf_token:
            raise RuntimeError("HF_TOKEN environment variable is not set")
        self._client = AsyncInferenceClient(
            token=hf_token, model=model, provider=inference_provider  # type: ignore[arg-type]
        )
        self._model = model
        logger.info(
            "HuggingFaceProvider initialized with model=%s, inference_provider=%s",
            model,
            inference_provider,
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

        openai_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        for msg in messages:
            openai_messages.append({"role": msg.role, "content": msg.content})

        function_choice = ChatCompletionInputFunctionName(name=tool_name)  # pyright: ignore[reportCallIssue]  # fmt: skip
        tool_choice = ChatCompletionInputToolChoiceClass(function=function_choice)  # pyright: ignore[reportCallIssue]  # fmt: skip
        kwargs: dict[str, Any] = {
            "messages": openai_messages,
            "max_tokens": resolve_max_tokens(),
            "stream": False,
            "tools": [tool_def],
            "tool_choice": tool_choice,
        }

        logger.debug(
            "Calling HuggingFace API (structured): model=%s, schema=%s",
            self._model,
            tool_name,
        )
        response = await _chat_completion_with_retry(client=self._client, kwargs=kwargs)

        if response.usage is not None:
            self._record_usage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )

        choice = response.choices[0]
        message = choice.message

        if message.tool_calls is not None:
            for tc in message.tool_calls:
                if tc.function.name == tool_name:
                    arguments = json.loads(tc.function.arguments)
                    return output_schema.model_validate(arguments)

        raise ValueError(f"LLM response did not contain a {tool_name} tool call")


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
