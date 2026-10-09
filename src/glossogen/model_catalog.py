"""The models and providers a run can be launched with.

The hosted entries are the models the run and evaluation pickers offer. Self-hosted
models are discovered from the ``SELF_HOSTED_BASE_URLS`` environment variable (a
JSON object mapping model name → endpoint URL), so adding a self-hosted deployment
needs no code change here. Prices live elsewhere: see ``token_pricing``.
"""

import json
import logging
import os
from enum import StrEnum
from typing import cast

logger = logging.getLogger(__name__)


class Provider(StrEnum):
    """Every provider name the platform knows, as pydantic-ai and the judge factory spell them."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE_GLA = "google-gla"
    OLLAMA = "ollama"
    SELF_HOSTED = "self-hosted"
    HUGGINGFACE = "huggingface"


# The providers a simulation agent, a scheduled swap or a replacement agent can run
# under: the ones the agent runner builds a pydantic-ai model for.
SIMULATION_PROVIDERS: tuple[Provider, ...] = (
    Provider.ANTHROPIC,
    Provider.OPENAI,
    Provider.GOOGLE_GLA,
    Provider.OLLAMA,
    Provider.SELF_HOSTED,
)

# The providers an LLM judge can run under: the ones ``create_provider`` builds.
JUDGE_PROVIDERS: tuple[Provider, ...] = (
    Provider.ANTHROPIC,
    Provider.HUGGINGFACE,
    Provider.OPENAI,
)


# (model, provider) pairs offered for hosted APIs. Model names use dashes, matching
# the IDs the APIs accept.
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
)


def _get_self_hosted_model_names() -> list[str]:
    """Return model names listed in the ``SELF_HOSTED_BASE_URLS`` env var.

    Returns an empty list when the env var is unset, empty, or not valid JSON,
    so that environments without a self-hosted endpoint do not raise.
    """
    raw = os.environ.get("SELF_HOSTED_BASE_URLS", "")
    if not raw:
        return []
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("SELF_HOSTED_BASE_URLS is not valid JSON; ignoring")
        return []
    if not isinstance(parsed, dict):
        logger.warning(
            "SELF_HOSTED_BASE_URLS must map model names to non-empty endpoint URLs; ignoring"
        )
        return []
    untyped_mapping = cast(dict[object, object], parsed)
    if not all(
        isinstance(name, str) and isinstance(url, str) and bool(url.strip())
        for name, url in untyped_mapping.items()
    ):
        logger.warning(
            "SELF_HOSTED_BASE_URLS must map model names to non-empty endpoint URLs; ignoring"
        )
        return []
    return list(cast(dict[str, str], untyped_mapping))


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
