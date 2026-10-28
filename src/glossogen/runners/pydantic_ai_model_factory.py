"""Constructs the ``model`` and ``ModelSettings`` arguments for a pydantic-ai ``Agent``.

Centralizes the per-provider mapping (Anthropic, OpenAI, self-hosted, etc.) so
the simulation runner, the probe metrics and the LLM judges get the same
provider defaults, and all but a HuggingFace judge build their models here.
"""

import os
from collections.abc import Sequence

from pydantic_ai.models import ModelRequestParameters, infer_model
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModelSettings
from pydantic_ai.profiles.openai import openai_model_profile
from pydantic_ai.providers.openai import OpenAIProvider as PydanticAIOpenAIProvider
from pydantic_ai.settings import ModelSettings, ThinkingLevel, merge_model_settings

from glossogen.model_catalog import (
    SELF_HOSTED_API_KEY_VAR,
    SELF_HOSTED_BASE_URLS_VAR,
    Provider,
    provider_spec,
)
from glossogen.models.agent_model_settings import AgentModelSettings
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


def thinking_reaches_model(model: str, provider: Provider, thinking: ThinkingLevel) -> bool:
    """Return whether pydantic-ai puts ``thinking`` into this model's requests.

    pydantic-ai drops the setting before the request when the model's profile does
    not mark it as able to think, and drops ``False`` when the profile says it
    always thinks. Asking ``prepare_request`` reads that decision instead of
    restating it. Builds the model's client, so the provider's credentials must be
    set; it makes no call.
    """
    built = infer_model(model=build_pydantic_ai_model(model=model, provider=provider))
    _, parameters = built.prepare_request(
        model_settings=ModelSettings(thinking=thinking),
        model_request_parameters=ModelRequestParameters(),
    )
    return parameters.thinking is not None


def default_pydantic_ai_settings(provider: Provider, model: str) -> ModelSettings:
    """Return the per-provider default ``ModelSettings`` the runner, probes and judges share.

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
    effort is set here: each model reasons at its own default unless the agent's
    settings name a ``thinking`` level.

    No output cap is set for any provider. Agents always send their own; a judge
    or a probe that sends none gets the provider's, which on Anthropic is the
    model's maximum output (pydantic-ai sends it) and on OpenAI the model's limit.
    """
    if provider == Provider.ANTHROPIC:
        return AnthropicModelSettings(
            anthropic_cache=True,
            anthropic_cache_instructions=True,
            anthropic_cache_tool_definitions=True,
        )
    if provider == Provider.OPENAI and _openai_model_reasons(model=model):
        return OpenAIResponsesModelSettings(openai_reasoning_summary="detailed")
    return ModelSettings()


def agent_model_settings(
    provider: Provider,
    model: str,
    settings: AgentModelSettings,
) -> ModelSettings:
    """Return the settings a simulation agent runs with.

    The provider defaults from :func:`default_pydantic_ai_settings`, then the
    ``settings`` the run was started with, of which only the ones set are sent
    and which win over the defaults. A scenario's own choices reach ``settings``
    through its preset knobs.
    """
    return layered_model_settings(
        layers=(
            default_pydantic_ai_settings(provider=provider, model=model),
            settings.to_pydantic_ai(),
        )
    )


def layered_model_settings(layers: Sequence[ModelSettings]) -> ModelSettings:
    """Merge ``layers`` with pydantic-ai's ``merge_model_settings``, later ones winning."""
    merged = ModelSettings()
    for layer in layers:
        merged = merge_model_settings(merged, layer) or ModelSettings()
    return merged


def _openai_model_reasons(model: str) -> bool:
    """Return whether pydantic-ai's profile marks this OpenAI model as a reasoning model.

    A fine-tune, named ``ft:<base model>:<org>:<suffix>:<id>``, is looked up by its
    base model, since the profile matches on the name's leading characters.
    """
    profiled_name = model
    if model.startswith(_OPENAI_FINE_TUNE_PREFIX):
        profiled_name = model.split(":")[1]
    return openai_model_profile(profiled_name).get("openai_supports_reasoning", False)
