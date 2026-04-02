"""Per-model token pricing table and lookup.

Provides USD-per-million-token rates for supported LLM models.
Used by both the agent runner (simulation cost tracking) and the
evaluation module (evaluator cost reporting).
"""

import logging
from typing import NamedTuple

logger = logging.getLogger(__name__)


class TokenPricing(NamedTuple):
    """Per-million-token prices in USD for a model, plus its provider."""

    provider: str
    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float
    cache_write_per_mtok: float


# Per-million-token prices in USD keyed by model name prefix.
# Prefix matching allows versioned IDs like "claude-sonnet-4-20250514"
# to match "claude-sonnet-4".
_PRICING_TABLE: dict[str, TokenPricing] = {
    # Anthropic — keys use dashes (matching actual API model IDs).
    # Longer prefixes first so "claude-opus-4-6-*" doesn't accidentally
    # match the cheaper "claude-opus-4" entry.
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
    "claude-opus-4": TokenPricing(
        provider="anthropic",
        input_per_mtok=15.0,
        output_per_mtok=75.0,
        cache_read_per_mtok=1.50,
        cache_write_per_mtok=18.75,
    ),
    "claude-sonnet-4-6": TokenPricing(
        provider="anthropic",
        input_per_mtok=3.0,
        output_per_mtok=15.0,
        cache_read_per_mtok=0.30,
        cache_write_per_mtok=3.75,
    ),
    "claude-sonnet-4": TokenPricing(
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
    "claude-haiku-3-5": TokenPricing(
        provider="anthropic",
        input_per_mtok=0.80,
        output_per_mtok=4.0,
        cache_read_per_mtok=0.08,
        cache_write_per_mtok=1.0,
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
    "gpt-4.1-nano": TokenPricing(
        provider="openai",
        input_per_mtok=0.10,
        output_per_mtok=0.40,
        cache_read_per_mtok=0.025,
        cache_write_per_mtok=0.10,
    ),
    "gpt-4.1-mini": TokenPricing(
        provider="openai",
        input_per_mtok=0.40,
        output_per_mtok=1.60,
        cache_read_per_mtok=0.10,
        cache_write_per_mtok=0.40,
    ),
    "gpt-4.1": TokenPricing(
        provider="openai",
        input_per_mtok=2.0,
        output_per_mtok=8.0,
        cache_read_per_mtok=0.50,
        cache_write_per_mtok=2.0,
    ),
    "gpt-4o-mini": TokenPricing(
        provider="openai",
        input_per_mtok=0.15,
        output_per_mtok=0.60,
        cache_read_per_mtok=0.075,
        cache_write_per_mtok=0.15,
    ),
    "gpt-4o": TokenPricing(
        provider="openai",
        input_per_mtok=2.50,
        output_per_mtok=10.0,
        cache_read_per_mtok=1.25,
        cache_write_per_mtok=2.50,
    ),
    "o4-mini": TokenPricing(
        provider="openai",
        input_per_mtok=1.10,
        output_per_mtok=4.40,
        cache_read_per_mtok=0.275,
        cache_write_per_mtok=1.10,
    ),
    "o3": TokenPricing(
        provider="openai",
        input_per_mtok=2.0,
        output_per_mtok=8.0,
        cache_read_per_mtok=0.50,
        cache_write_per_mtok=2.0,
    ),
}


def list_providers() -> list[str]:
    """Return the unique provider names from the pricing table, preserving insertion order."""
    seen: set[str] = set()
    providers: list[str] = []
    for pricing in _PRICING_TABLE.values():
        if pricing.provider not in seen:
            seen.add(pricing.provider)
            providers.append(pricing.provider)
    return providers


def list_models() -> list[tuple[str, str]]:
    """Return all known model prefixes with their providers.

    Returns a list of (model_prefix, provider) pairs, ordered as they
    appear in the pricing table.
    """
    return [(prefix, pricing.provider) for prefix, pricing in _PRICING_TABLE.items()]


def find_pricing(model: str) -> TokenPricing | None:
    """Find pricing by matching model name against prefix keys.

    Normalizes dots to dashes before comparison so that both
    ``claude-haiku-4.5`` and ``claude-haiku-4-5-20251001`` match.
    """
    normalized = model.replace(".", "-")
    for prefix, pricing in _PRICING_TABLE.items():
        if normalized.startswith(prefix.replace(".", "-")):
            return pricing
    return None
