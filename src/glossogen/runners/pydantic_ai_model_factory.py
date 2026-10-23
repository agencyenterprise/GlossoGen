"""Constructs the ``model`` and ``ModelSettings`` arguments for a pydantic-ai ``Agent``.

Centralizes the per-provider mapping (Anthropic, OpenAI, self-hosted, etc.) so
both the simulation runner and the post-simulation probe metric instantiate
agents the same way.
"""

import os
from typing import cast

from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModelSettings
from pydantic_ai.profiles.openai import openai_model_profile
from pydantic_ai.providers.openai import OpenAIProvider as PydanticAIOpenAIProvider
from pydantic_ai.settings import ModelSettings, ThinkingLevel

from glossogen.model_catalog import (
    SELF_HOSTED_API_KEY_VAR,
    SELF_HOSTED_BASE_URLS_VAR,
    Provider,
    provider_spec,
)
from glossogen.self_hosted_config import parse_self_hosted_base_urls

_OPENAI_FINE_TUNE_PREFIX = "ft:"


def resolve_self_hosted_base_url(model: str) -> str:
    """Look up the OpenAI-compatible base URL for a self-hosted model.

    Reads ``SELF_HOSTED_BASE_URLS`` from the environment, expecting a JSON
    object mapping model names (as passed to the simulation) to their
    serving endpoints.
    """
    mapping = parse_self_hosted_base_urls(raw=os.environ[SELF_HOSTED_BASE_URLS_VAR])
    if model not in mapping:
        configured = ", ".join(sorted(mapping)) or "<none>"
        raise KeyError(
            f"Self-hosted model {model!r} has no entry in SELF_HOSTED_BASE_URLS "
            f"(configured models: {configured})"
        )
    return mapping[model]


def build_pydantic_ai_model(model: str, provider: Provider) -> str | OpenAIChatModel:
    """Return the ``model`` argument for a pydantic-ai ``Agent`` constructor.

    For ``self-hosted`` providers the function returns a fully-constructed
    ``OpenAIChatModel`` pointing at the OpenAI-compatible base URL. For all
    other providers it returns the ``"<prefix>:<model>"`` string literal that
    pydantic-ai uses to look up the right backend, with the prefix from the
    provider's row in ``PROVIDER_SPECS``.
    """
    spec = provider_spec(provider=provider)
    if spec is None:
        raise ValueError(f"no agent runs under provider {provider!r}")
    if spec.pydantic_ai_prefix is None:
        base_url = resolve_self_hosted_base_url(model=model)
        oai_provider = PydanticAIOpenAIProvider(
            base_url=base_url,
            api_key=os.environ[SELF_HOSTED_API_KEY_VAR],
        )
        return OpenAIChatModel(model, provider=oai_provider)
    return f"{spec.pydantic_ai_prefix}:{model}"


def default_pydantic_ai_settings(provider: Provider, model: str) -> ModelSettings:
    """Return the per-provider default ``ModelSettings`` used by both the runner and probes.

    On Anthropic we enable automatic prompt caching (``anthropic_cache=True``)
    rather than the per-block ``anthropic_cache_messages``. Auto mode passes a
    top-level ``cache_control`` parameter so the server caches the longest
    matching prefix across calls, which matters when many calls share the same
    ``system + history`` prefix but vary the trailing user prompt (e.g. the
    probe metric calls the whole question bank per agent).

    On OpenAI a reasoning model gets a detailed reasoning summary, which decides
    whether reasoning text comes back, not how much the model reasons. It is sent
    only to a model pydantic-ai's profile marks as a reasoning model, since
    pydantic-ai sends it whenever it is set, whatever the model. No reasoning
    effort is set here: each model reasons at its own default unless the caller
    sets ``thinking``.
    """
    if provider == Provider.ANTHROPIC:
        return AnthropicModelSettings(
            anthropic_cache=True,
            anthropic_cache_instructions=True,
            anthropic_cache_tool_definitions=True,
        )
    if provider == Provider.OPENAI:
        # Reasoning models consume output tokens for both the internal reasoning
        # and the visible response; the provider default (≈4096 max_output) is
        # easy to exhaust on long structured outputs before any visible text
        # is emitted. 32k gives plenty of headroom without runaway costs.
        if not openai_model_reasons(model=model):
            return OpenAIResponsesModelSettings(max_tokens=32768)
        return OpenAIResponsesModelSettings(
            openai_reasoning_summary="detailed",
            max_tokens=32768,
        )
    return ModelSettings()


def agent_model_settings(
    provider: Provider,
    model: str,
    parallel_tool_calls: bool,
    thinking: ThinkingLevel | None,
) -> ModelSettings:
    """Return the settings a simulation agent runs with.

    The provider defaults from :func:`default_pydantic_ai_settings`, plus
    ``parallel_tool_calls=False`` when the scenario allows one tool call per
    model response. When parallel calls are allowed the key is left out, so the
    provider's own default applies. ``thinking`` goes to pydantic-ai's unified
    field when it is set, and is left out otherwise.
    """
    settings = default_pydantic_ai_settings(provider=provider, model=model)
    if not parallel_tool_calls:
        settings["parallel_tool_calls"] = False
    return with_thinking(settings=settings, thinking=thinking)


def with_thinking(settings: ModelSettings, thinking: ThinkingLevel | None) -> ModelSettings:
    """Return ``settings`` with ``thinking`` set, or unchanged when it is ``None``."""
    if thinking is None:
        return settings
    return cast(ModelSettings, {**settings, "thinking": thinking})


def openai_model_reasons(model: str) -> bool:
    """Return whether pydantic-ai's profile marks this OpenAI model as a reasoning model.

    A fine-tune, named ``ft:<base model>:<org>:<suffix>:<id>``, is looked up by its
    base model, since the profile matches on the name's leading characters.
    """
    profiled_name = model
    if model.startswith(_OPENAI_FINE_TUNE_PREFIX):
        profiled_name = model.split(":")[1]
    return openai_model_profile(profiled_name).get("openai_supports_reasoning", False)
