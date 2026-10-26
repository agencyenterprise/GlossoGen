"""The models and providers a run can be launched with.

``PROVIDER_SPECS`` has one row per provider an agent can run under: the variables
that carry its credential, the model prefix pydantic-ai reaches it by, whether its
tokens are billed, and whether it serves open- or closed-weight models. The launch
check, the model factory, pricing and the ``model_class`` export column read it.
Adding a provider that pydantic-ai and ``genai-prices`` already support takes a
value in ``Provider``, a row here, and the pydantic-ai extra for its SDK in
``pyproject.toml`` when it needs one. Behaviour that differs by provider beyond
those fields, such as default model settings or history compaction, is keyed on
the provider where it is implemented.

The hosted entries are the models the run picker offers; the evaluation picker
offers those whose provider is a judge provider. Self-hosted models are discovered
from the ``SELF_HOSTED_BASE_URLS`` environment variable (a JSON object mapping
model name → endpoint URL), so adding a self-hosted deployment needs no code change
here. Prices live elsewhere: see ``token_pricing``.
"""

import logging
import os
from enum import StrEnum
from typing import NamedTuple

from glossogen.self_hosted_config import parse_self_hosted_base_urls

logger = logging.getLogger(__name__)


class Provider(StrEnum):
    """Every provider name the platform knows, as pydantic-ai and the judge factory spell them."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE_GLA = "google-gla"
    XAI = "xai"
    GROQ = "groq"
    MISTRAL = "mistral"
    DEEPSEEK = "deepseek"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    SELF_HOSTED = "self-hosted"
    HUGGINGFACE = "huggingface"


SELF_HOSTED_BASE_URLS_VAR = "SELF_HOSTED_BASE_URLS"
SELF_HOSTED_API_KEY_VAR = "SELF_HOSTED_API_KEY"
OLLAMA_BASE_URL_VAR = "OLLAMA_BASE_URL"


class CredentialRequirement(NamedTuple):
    """Environment variables that each satisfy one credential a provider reads.

    Any one of ``accepted_names`` carrying a value satisfies the requirement. A
    provider that reads two independent values declares two requirements.
    """

    accepted_names: tuple[str, ...]


class WeightClass(StrEnum):
    """Whether a provider's models are open-weight or closed."""

    OPEN = "open"
    CLOSED = "closed"


class ProviderSpec(NamedTuple):
    """What the platform needs to know to run an agent under one provider.

    ``pydantic_ai_prefix`` is the ``<prefix>:<model>`` name pydantic-ai builds the
    model from, or None for ``self-hosted``, whose model the factory builds itself.
    ``billed`` is False for a provider served on hardware billed elsewhere, priced
    at zero. ``weights`` is None for a provider serving both open- and
    closed-weight models, so its runs are left unclassified rather than guessed.
    """

    provider: Provider
    credentials: tuple[CredentialRequirement, ...]
    pydantic_ai_prefix: str | None
    billed: bool
    weights: WeightClass | None


PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        provider=Provider.ANTHROPIC,
        credentials=(CredentialRequirement(accepted_names=("ANTHROPIC_API_KEY",)),),
        pydantic_ai_prefix="anthropic",
        billed=True,
        weights=WeightClass.CLOSED,
    ),
    ProviderSpec(
        provider=Provider.OPENAI,
        credentials=(CredentialRequirement(accepted_names=("OPENAI_API_KEY",)),),
        pydantic_ai_prefix="openai-responses",
        billed=True,
        weights=WeightClass.CLOSED,
    ),
    # ``google-gla`` is Glossogen's stable name; pydantic-ai 2.x reaches the Gemini
    # Developer API under the ``google`` prefix.
    ProviderSpec(
        provider=Provider.GOOGLE_GLA,
        credentials=(CredentialRequirement(accepted_names=("GOOGLE_API_KEY", "GEMINI_API_KEY")),),
        pydantic_ai_prefix="google",
        billed=True,
        weights=WeightClass.CLOSED,
    ),
    ProviderSpec(
        provider=Provider.XAI,
        credentials=(CredentialRequirement(accepted_names=("XAI_API_KEY",)),),
        pydantic_ai_prefix="xai",
        billed=True,
        weights=WeightClass.CLOSED,
    ),
    ProviderSpec(
        provider=Provider.GROQ,
        credentials=(CredentialRequirement(accepted_names=("GROQ_API_KEY",)),),
        pydantic_ai_prefix="groq",
        billed=True,
        weights=WeightClass.OPEN,
    ),
    ProviderSpec(
        provider=Provider.MISTRAL,
        credentials=(CredentialRequirement(accepted_names=("MISTRAL_API_KEY",)),),
        pydantic_ai_prefix="mistral",
        billed=True,
        weights=None,
    ),
    ProviderSpec(
        provider=Provider.DEEPSEEK,
        credentials=(CredentialRequirement(accepted_names=("DEEPSEEK_API_KEY",)),),
        pydantic_ai_prefix="deepseek",
        billed=True,
        weights=WeightClass.OPEN,
    ),
    ProviderSpec(
        provider=Provider.OPENROUTER,
        credentials=(CredentialRequirement(accepted_names=("OPENROUTER_API_KEY",)),),
        pydantic_ai_prefix="openrouter",
        billed=True,
        weights=None,
    ),
    ProviderSpec(
        provider=Provider.OLLAMA,
        credentials=(CredentialRequirement(accepted_names=(OLLAMA_BASE_URL_VAR,)),),
        pydantic_ai_prefix="ollama",
        billed=False,
        weights=WeightClass.OPEN,
    ),
    # Which endpoint serves a self-hosted model depends on the model's name, so
    # the launch check looks it up in ``SELF_HOSTED_BASE_URLS`` itself.
    ProviderSpec(
        provider=Provider.SELF_HOSTED,
        credentials=(
            CredentialRequirement(accepted_names=(SELF_HOSTED_BASE_URLS_VAR,)),
            CredentialRequirement(accepted_names=(SELF_HOSTED_API_KEY_VAR,)),
        ),
        pydantic_ai_prefix=None,
        billed=False,
        weights=WeightClass.OPEN,
    ),
)

_SPECS_BY_PROVIDER: dict[Provider, ProviderSpec] = {spec.provider: spec for spec in PROVIDER_SPECS}

# The providers a simulation agent, a scheduled swap or a replacement agent can run
# under: the ones the agent runner builds a pydantic-ai model for.
SIMULATION_PROVIDERS: tuple[Provider, ...] = tuple(spec.provider for spec in PROVIDER_SPECS)

# The providers serving open-weight models, and those serving closed-weight ones.
# A provider serving both, such as ``openrouter``, is in neither.
OPEN_WEIGHT_PROVIDERS: frozenset[Provider] = frozenset(
    spec.provider for spec in PROVIDER_SPECS if spec.weights is WeightClass.OPEN
)
CLOSED_WEIGHT_PROVIDERS: frozenset[Provider] = frozenset(
    spec.provider for spec in PROVIDER_SPECS if spec.weights is WeightClass.CLOSED
)


def provider_spec(provider: Provider) -> ProviderSpec | None:
    """The spec for ``provider``, or None for one no agent runs under (a judge-only one)."""
    return _SPECS_BY_PROVIDER.get(provider)


# The providers an LLM judge can run under: the ones ``create_judge_provider`` builds.
JUDGE_PROVIDERS: tuple[Provider, ...] = (
    Provider.ANTHROPIC,
    Provider.HUGGINGFACE,
    Provider.OPENAI,
)


# (model, provider) pairs offered for hosted APIs. Each model name is the ID its
# provider's API accepts.
_HOSTED_MODELS: tuple[tuple[str, Provider], ...] = (
    ("claude-opus-4-7", Provider.ANTHROPIC),
    ("claude-opus-4-6", Provider.ANTHROPIC),
    ("claude-opus-4-5", Provider.ANTHROPIC),
    ("claude-sonnet-4-6", Provider.ANTHROPIC),
    ("claude-haiku-4-5", Provider.ANTHROPIC),
    ("gpt-5.4-nano", Provider.OPENAI),
    ("gpt-5.4-mini", Provider.OPENAI),
    ("gpt-5.4", Provider.OPENAI),
    ("gpt-5.2", Provider.OPENAI),
    ("grok-4.6", Provider.XAI),
    ("llama-3.3-70b-versatile", Provider.GROQ),
    ("mistral-large-latest", Provider.MISTRAL),
    ("deepseek-chat", Provider.DEEPSEEK),
    ("deepseek/deepseek-chat-v3.1", Provider.OPENROUTER),
)


def _get_self_hosted_model_names() -> list[str]:
    """Return model names listed in the ``SELF_HOSTED_BASE_URLS`` env var.

    Returns an empty list when the env var is unset, empty, or not valid JSON,
    so that environments without a self-hosted endpoint do not raise.
    """
    raw = os.environ.get(SELF_HOSTED_BASE_URLS_VAR, "")
    if not raw:
        return []
    try:
        return list(parse_self_hosted_base_urls(raw=raw))
    except ValueError:
        logger.exception(
            "SELF_HOSTED_BASE_URLS must map model names to non-empty endpoint URLs; ignoring"
        )
        return []


def list_providers() -> list[Provider]:
    """The providers the pickers offer: those of the hosted models, then ``self-hosted``.

    ``self-hosted`` is listed only when ``SELF_HOSTED_BASE_URLS`` names at least
    one model. This is the picker listing, not the set a run may name: that is
    ``SIMULATION_PROVIDERS``.
    """
    seen: set[Provider] = set()
    providers: list[Provider] = []
    for _, provider in _HOSTED_MODELS:
        if provider not in seen:
            seen.add(provider)
            providers.append(provider)
    if _get_self_hosted_model_names():
        providers.append(Provider.SELF_HOSTED)
    return providers


def list_models() -> list[tuple[str, Provider]]:
    """Return every offered (model, provider) pair.

    The hosted models come first, followed by every model listed in
    ``SELF_HOSTED_BASE_URLS``.
    """
    self_hosted = [(name, Provider.SELF_HOSTED) for name in _get_self_hosted_model_names()]
    return list(_HOSTED_MODELS) + self_hosted


def list_judge_models() -> list[tuple[str, Provider]]:
    """Return the offered (model, provider) pairs whose provider an LLM judge can run under."""
    return [(model, provider) for model, provider in list_models() if provider in JUDGE_PROVIDERS]
