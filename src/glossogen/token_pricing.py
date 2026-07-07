"""Per-model token pricing table and lookup.

Provides USD-per-million-token rates for supported LLM models.
Used by both the agent runner (simulation cost tracking) and the
evaluation module (evaluator cost reporting).

Self-hosted models are discovered dynamically from the ``SELF_HOSTED_BASE_URLS``
environment variable (a JSON object mapping model name → endpoint URL), so
adding a new self-hosted deployment does not require code changes here.
"""

import json
import logging
import os
from typing import NamedTuple

logger = logging.getLogger(__name__)

SELF_HOSTED_PROVIDER = "self-hosted"


class TokenPricing(NamedTuple):
    """Per-million-token prices in USD for a model, plus its provider."""

    provider: str
    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float
    cache_write_per_mtok: float


# Per-million-token prices in USD keyed by model name prefix for hosted APIs.
# Self-hosted models are NOT listed here — they are discovered from
# ``SELF_HOSTED_BASE_URLS`` at request time and priced at $0 (GPU-time billed
# elsewhere). Prefix matching allows versioned IDs like
# ``claude-sonnet-4-20250514`` to match ``claude-sonnet-4``.
_PRICING_TABLE: dict[str, TokenPricing] = {
    # Anthropic — keys use dashes (matching actual API model IDs).
    # Longer prefixes first so "claude-opus-4-6-*" doesn't accidentally
    # match the cheaper "claude-opus-4" entry.
    "claude-opus-4-7": TokenPricing(
        provider="anthropic",
        input_per_mtok=5.0,
        output_per_mtok=25.0,
        cache_read_per_mtok=0.50,
        cache_write_per_mtok=6.25,
    ),
    "claude-opus-4-6": TokenPricing(
        provider="anthropic",
        input_per_mtok=5.0,
        output_per_mtok=25.0,
        cache_read_per_mtok=0.50,
        cache_write_per_mtok=6.25,
    ),
    "claude-opus-4-5": TokenPricing(
        provider="anthropic",
        input_per_mtok=5.0,
        output_per_mtok=25.0,
        cache_read_per_mtok=0.50,
        cache_write_per_mtok=6.25,
    ),
    "claude-sonnet-4-6": TokenPricing(
        provider="anthropic",
        input_per_mtok=3.0,
        output_per_mtok=15.0,
        cache_read_per_mtok=0.30,
        cache_write_per_mtok=3.75,
    ),
    "claude-haiku-4-5": TokenPricing(
        provider="anthropic",
        input_per_mtok=1.0,
        output_per_mtok=5.0,
        cache_read_per_mtok=0.10,
        cache_write_per_mtok=1.25,
    ),
    # OpenAI — longer prefixes first so "gpt-5.4-mini" doesn't match "gpt-5.4".
    "gpt-5.4-nano": TokenPricing(
        provider="openai",
        input_per_mtok=0.20,
        output_per_mtok=1.25,
        cache_read_per_mtok=0.02,
        cache_write_per_mtok=0.20,
    ),
    "gpt-5.4-mini": TokenPricing(
        provider="openai",
        input_per_mtok=0.75,
        output_per_mtok=4.50,
        cache_read_per_mtok=0.075,
        cache_write_per_mtok=0.75,
    ),
    "gpt-5.4": TokenPricing(
        provider="openai",
        input_per_mtok=2.50,
        output_per_mtok=15.0,
        cache_read_per_mtok=0.25,
        cache_write_per_mtok=2.50,
    ),
    "gpt-5.2": TokenPricing(
        provider="openai",
        input_per_mtok=0.875,
        output_per_mtok=7.0,
        cache_read_per_mtok=0.175,
        cache_write_per_mtok=0.875,
    ),
}


_SELF_HOSTED_PRICING = TokenPricing(
    provider=SELF_HOSTED_PROVIDER,
    input_per_mtok=0.0,
    output_per_mtok=0.0,
    cache_read_per_mtok=0.0,
    cache_write_per_mtok=0.0,
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
        parsed: dict[str, str] = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("SELF_HOSTED_BASE_URLS is not valid JSON; ignoring.")
        return []
    return list(parsed.keys())


def list_providers() -> list[str]:
    """Return unique provider names, including ``self-hosted`` if any are configured.

    The order is: providers from the static pricing table (in insertion
    order), then ``self-hosted`` last when ``SELF_HOSTED_BASE_URLS`` lists
    at least one model.
    """
    seen: set[str] = set()
    providers: list[str] = []
    for pricing in _PRICING_TABLE.values():
        if pricing.provider not in seen:
            seen.add(pricing.provider)
            providers.append(pricing.provider)
    if _get_self_hosted_model_names():
        providers.append(SELF_HOSTED_PROVIDER)
    return providers


def list_models() -> list[tuple[str, str]]:
    """Return all known (model_prefix, provider) pairs.

    Includes static pricing-table entries followed by every model listed
    in ``SELF_HOSTED_BASE_URLS``.
    """
    static_models = [(prefix, pricing.provider) for prefix, pricing in _PRICING_TABLE.items()]
    self_hosted = [(name, SELF_HOSTED_PROVIDER) for name in _get_self_hosted_model_names()]
    return static_models + self_hosted


def find_pricing(model: str) -> TokenPricing | None:
    """Find pricing by matching model name against prefix keys.

    Normalizes dots to dashes before comparison so that both
    ``claude-haiku-4.5`` and ``claude-haiku-4-5-20251001`` match. Falls
    back to a zero-cost ``self-hosted`` pricing entry when the model is
    listed in ``SELF_HOSTED_BASE_URLS``.
    """
    normalized = model.replace(".", "-")
    for prefix, pricing in _PRICING_TABLE.items():
        if normalized.startswith(prefix.replace(".", "-")):
            return pricing
    if model in _get_self_hosted_model_names():
        return _SELF_HOSTED_PRICING
    return None
