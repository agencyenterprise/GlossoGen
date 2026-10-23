"""The platform's LLM judges, run through pydantic-ai.

``create_judge_provider`` builds the ``LLMProvider`` every judge calls: the
round judges scenarios hold and the LLM-judge metrics of ``glossogen evaluate``.
Judges go through the same model factory and provider defaults as the
simulation agents and the probes, and take their settings as a
``JudgeModelSettings``, which has the agents' fields.

Each ``generate_structured`` call runs a tool-less ``Agent`` whose output is a
tool shaped like the requested schema. A response that fails validation is sent
back to the model with the error, and a rate limit or server error retries the
whole request.
"""

import logging

from pydantic_ai import Agent, AgentRunResult, ToolOutput
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart
from pydantic_ai.models import Model, infer_model
from pydantic_ai.models.huggingface import HuggingFaceModel
from pydantic_ai.providers.huggingface import HuggingFaceProvider
from pydantic_ai.settings import ModelSettings
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from glossogen.llm.provider import LLMMessage, LLMProvider, SamplingParams, T
from glossogen.llm.run_usage_projection import evaluation_token_usage
from glossogen.model_catalog import JUDGE_PROVIDERS, Provider
from glossogen.models.agent_model_settings import JudgeModelSettings
from glossogen.runners.pydantic_ai_model_factory import (
    build_pydantic_ai_model,
    default_pydantic_ai_settings,
    layered_model_settings,
)

logger = logging.getLogger(__name__)

JUDGE_REQUEST_ATTEMPTS = 3
"""Attempts at one judge call when the provider answers 429 or 5xx."""

JUDGE_OUTPUT_RETRIES = 2
"""Times a response that fails schema validation is returned to the model."""


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Return True for a rate-limit (429) or server (5xx) response."""
    if not isinstance(exc, ModelHTTPError):
        return False
    return exc.status_code == 429 or exc.status_code >= 500


class PydanticAIJudgeProvider(LLMProvider):
    """An ``LLMProvider`` that answers each structured call with one pydantic-ai run."""

    def __init__(self, model: Model, model_settings: ModelSettings) -> None:
        """Hold the model and the settings every call is sent with."""
        super().__init__()
        self._model = model
        self._model_settings = model_settings

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[T],
        sampling: SamplingParams | None = None,
    ) -> T:
        """Run the conversation and return the model's answer as ``output_schema``.

        ``sampling`` replaces the temperature in the provider's settings for this
        call only. pydantic-ai leaves out a setting the model does not accept.
        """
        model_settings = self._model_settings
        if sampling is not None:
            model_settings = layered_model_settings(
                layers=(model_settings, ModelSettings(temperature=sampling.temperature))
            )
        agent: Agent[None, T] = Agent(
            model=self._model,
            system_prompt=system_prompt,
            output_type=ToolOutput(output_schema, name=output_schema.__name__),
            model_settings=model_settings,
            retries={"output": JUDGE_OUTPUT_RETRIES},
        )
        history, user_prompt = _split_conversation(messages=messages)
        result = await _run_with_retry(agent=agent, user_prompt=user_prompt, history=history)
        usage = evaluation_token_usage(run_usage=result.usage)
        self._record_usage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_input_tokens=usage.cache_read_input_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens,
        )
        return result.output


@retry(
    retry=retry_if_exception(_is_retryable_http_error),
    stop=stop_after_attempt(JUDGE_REQUEST_ATTEMPTS),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    reraise=True,
)
async def _run_with_retry(
    agent: Agent[None, T],
    user_prompt: str,
    history: list[ModelMessage],
) -> AgentRunResult[T]:
    """Run ``agent`` once, retrying the whole run on a 429 or 5xx response."""
    return await agent.run(user_prompt=user_prompt, message_history=history)


def _split_conversation(messages: list[LLMMessage]) -> tuple[list[ModelMessage], str]:
    """Return ``messages`` as pydantic-ai history plus the closing user prompt.

    The last message must be the user's. Earlier ones are ``user`` or
    ``assistant`` turns.
    """
    if not messages or messages[-1].role != "user":
        raise ValueError("a judge conversation must end with a user message")
    history: list[ModelMessage] = []
    for message in messages[:-1]:
        if message.role == "user":
            history.append(ModelRequest.user_text_prompt(message.content))
        elif message.role == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=message.content)]))
        else:
            raise ValueError(f"a judge message has role {message.role!r}; use user or assistant")
    return history, messages[-1].content


def create_judge_provider(
    provider_name: str,
    model: str,
    inference_provider: str | None,
    settings: JudgeModelSettings,
) -> LLMProvider:
    """Build the judge for ``model`` under ``provider_name``, sent ``settings`` on every call.

    The settings sit on top of the provider defaults the agents get from
    ``default_pydantic_ai_settings``. ``inference_provider`` routes a HuggingFace
    judge to one of HuggingFace's inference backends and is refused for any other
    provider. Building the model reads the provider's API key, so a missing key
    raises here.
    """
    if provider_name not in JUDGE_PROVIDERS:
        raise ValueError(
            f"Unknown provider '{provider_name}'. Judge providers: {', '.join(JUDGE_PROVIDERS)}"
        )
    provider = Provider(provider_name)
    logger.info(
        "Judge built with model=%s provider=%s settings=%s",
        model,
        provider,
        settings.model_dump(mode="json"),
    )
    return PydanticAIJudgeProvider(
        model=_build_judge_model(
            model=model, provider=provider, inference_provider=inference_provider
        ),
        model_settings=layered_model_settings(
            layers=(
                default_pydantic_ai_settings(provider=provider, model=model),
                settings.to_pydantic_ai(),
            )
        ),
    )


def _build_judge_model(model: str, provider: Provider, inference_provider: str | None) -> Model:
    """Return the pydantic-ai model a judge under ``provider`` calls."""
    if provider == Provider.HUGGINGFACE:
        if inference_provider is None:
            return HuggingFaceModel(model, provider=HuggingFaceProvider())
        return HuggingFaceModel(
            model, provider=HuggingFaceProvider(provider_name=inference_provider)
        )
    if inference_provider is not None:
        raise ValueError(
            f"an inference provider routes a HuggingFace judge; this judge runs under {provider}"
        )
    return infer_model(build_pydantic_ai_model(model=model, provider=provider))
