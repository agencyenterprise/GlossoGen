"""Constructs the ``model`` and ``ModelSettings`` arguments for a pydantic-ai ``Agent``.

Centralizes the per-provider mapping (Anthropic, OpenAI, self-hosted, etc.) so
both the simulation runner and the post-simulation probe metric instantiate
agents the same way.
"""

import json
import os

from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider as PydanticAIOpenAIProvider
from pydantic_ai.settings import ModelSettings


def resolve_self_hosted_base_url(model: str) -> str:
    """Look up the OpenAI-compatible base URL for a self-hosted model.

    Reads ``SELF_HOSTED_BASE_URLS`` from the environment, expecting a JSON
    object mapping model names (as passed to the simulation) to their
    serving endpoints.
    """
    raw = os.environ["SELF_HOSTED_BASE_URLS"]
    mapping: dict[str, str] = json.loads(raw)
    if model not in mapping:
        configured = ", ".join(sorted(mapping)) or "<none>"
        raise KeyError(
            f"Self-hosted model {model!r} has no entry in SELF_HOSTED_BASE_URLS "
            f"(configured models: {configured})"
        )
    return mapping[model]


def build_pydantic_ai_model(model: str, provider: str) -> str | OpenAIChatModel:
    """Return the ``model`` argument for a pydantic-ai ``Agent`` constructor.

    For ``self-hosted`` providers the function returns a fully-constructed
    ``OpenAIChatModel`` pointing at the OpenAI-compatible base URL. For all
    other providers it returns the ``"<prefix>:<model>"`` string literal that
    pydantic-ai uses to look up the right backend.
    """
    if provider == "self-hosted":
        base_url = resolve_self_hosted_base_url(model=model)
        oai_provider = PydanticAIOpenAIProvider(
            base_url=base_url,
            api_key=os.environ["SELF_HOSTED_API_KEY"],
        )
        return OpenAIChatModel(model, provider=oai_provider)
    if provider == "openai":
        model_prefix = "openai-responses"
    else:
        model_prefix = provider
    return f"{model_prefix}:{model}"


def default_pydantic_ai_settings(provider: str) -> ModelSettings:
    """Return the per-provider default ``ModelSettings`` used by both the runner and probes.

    On Anthropic we enable automatic prompt caching (``anthropic_cache=True``)
    rather than the per-block ``anthropic_cache_messages``. Auto mode passes a
    top-level ``cache_control`` parameter so the server caches the longest
    matching prefix across calls — important when many calls share the same
    ``system + history`` prefix but vary the trailing user prompt (e.g. the
    probe metric calls 28 questions per agent).
    """
    if provider == "anthropic":
        return AnthropicModelSettings(
            anthropic_cache=True,
            anthropic_cache_instructions=True,
            anthropic_cache_tool_definitions=True,
        )
    if provider == "openai":
        # Reasoning models consume output tokens for both the internal reasoning
        # and the visible response; the provider default (≈4096 max_output) is
        # easy to exhaust on long structured outputs before any visible text
        # is emitted. 32k gives plenty of headroom without runaway costs.
        return OpenAIResponsesModelSettings(
            openai_reasoning_effort="high",
            openai_reasoning_summary="concise",
            max_tokens=32768,
        )
    return ModelSettings()
