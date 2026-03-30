"""Pricing models and cost estimation for LLM evaluation calls."""

import logging
from typing import NamedTuple

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class TokenPricing(NamedTuple):
    """Per-million-token prices in USD for a model."""

    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float
    cache_write_per_mtok: float


class EvaluationTokenUsage(BaseModel):
    """Accumulated token counts across all LLM calls during an evaluation run."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


class EvaluationCost(BaseModel):
    """Token usage and estimated dollar cost for an evaluation run."""

    usage: EvaluationTokenUsage
    estimated_cost_usd: float
    model: str
    provider_name: str


# Per-million-token prices in USD keyed by model name prefix.
# Prefix matching allows versioned IDs like "claude-sonnet-4-20250514"
# to match "claude-sonnet-4".
_PRICING_TABLE: dict[str, TokenPricing] = {
    # Anthropic — longer prefixes first so "claude-opus-4.6-*" doesn't
    # accidentally match the cheaper "claude-opus-4" entry.
    "claude-opus-4.6": TokenPricing(
        input_per_mtok=5.0,
        output_per_mtok=25.0,
        cache_read_per_mtok=0.50,
        cache_write_per_mtok=6.25,
    ),
    "claude-opus-4.5": TokenPricing(
        input_per_mtok=5.0,
        output_per_mtok=25.0,
        cache_read_per_mtok=0.50,
        cache_write_per_mtok=6.25,
    ),
    "claude-opus-4": TokenPricing(
        input_per_mtok=15.0,
        output_per_mtok=75.0,
        cache_read_per_mtok=1.50,
        cache_write_per_mtok=18.75,
    ),
    "claude-sonnet-4.6": TokenPricing(
        input_per_mtok=3.0,
        output_per_mtok=15.0,
        cache_read_per_mtok=0.30,
        cache_write_per_mtok=3.75,
    ),
    "claude-sonnet-4": TokenPricing(
        input_per_mtok=3.0,
        output_per_mtok=15.0,
        cache_read_per_mtok=0.30,
        cache_write_per_mtok=3.75,
    ),
    "claude-haiku-4.5": TokenPricing(
        input_per_mtok=1.0,
        output_per_mtok=5.0,
        cache_read_per_mtok=0.10,
        cache_write_per_mtok=1.25,
    ),
    "claude-haiku-3.5": TokenPricing(
        input_per_mtok=0.80,
        output_per_mtok=4.0,
        cache_read_per_mtok=0.08,
        cache_write_per_mtok=1.0,
    ),
    # OpenAI — longer prefixes first so "gpt-5.4-mini" doesn't match "gpt-5.4".
    "gpt-5.4-nano": TokenPricing(
        input_per_mtok=0.20,
        output_per_mtok=1.25,
        cache_read_per_mtok=0.02,
        cache_write_per_mtok=0.20,
    ),
    "gpt-5.4-mini": TokenPricing(
        input_per_mtok=0.75,
        output_per_mtok=4.50,
        cache_read_per_mtok=0.075,
        cache_write_per_mtok=0.75,
    ),
    "gpt-5.4": TokenPricing(
        input_per_mtok=2.50,
        output_per_mtok=15.0,
        cache_read_per_mtok=0.25,
        cache_write_per_mtok=2.50,
    ),
    "gpt-5.2": TokenPricing(
        input_per_mtok=0.875,
        output_per_mtok=7.0,
        cache_read_per_mtok=0.175,
        cache_write_per_mtok=0.875,
    ),
    "gpt-4.1-nano": TokenPricing(
        input_per_mtok=0.10,
        output_per_mtok=0.40,
        cache_read_per_mtok=0.025,
        cache_write_per_mtok=0.10,
    ),
    "gpt-4.1-mini": TokenPricing(
        input_per_mtok=0.40,
        output_per_mtok=1.60,
        cache_read_per_mtok=0.10,
        cache_write_per_mtok=0.40,
    ),
    "gpt-4.1": TokenPricing(
        input_per_mtok=2.0,
        output_per_mtok=8.0,
        cache_read_per_mtok=0.50,
        cache_write_per_mtok=2.0,
    ),
    "gpt-4o-mini": TokenPricing(
        input_per_mtok=0.15,
        output_per_mtok=0.60,
        cache_read_per_mtok=0.075,
        cache_write_per_mtok=0.15,
    ),
    "gpt-4o": TokenPricing(
        input_per_mtok=2.50,
        output_per_mtok=10.0,
        cache_read_per_mtok=1.25,
        cache_write_per_mtok=2.50,
    ),
    "o4-mini": TokenPricing(
        input_per_mtok=1.10,
        output_per_mtok=4.40,
        cache_read_per_mtok=0.275,
        cache_write_per_mtok=1.10,
    ),
    "o3": TokenPricing(
        input_per_mtok=2.0,
        output_per_mtok=8.0,
        cache_read_per_mtok=0.50,
        cache_write_per_mtok=2.0,
    ),
}


def _find_pricing(model: str) -> TokenPricing | None:
    """Find pricing by matching model name against prefix keys."""
    for prefix, pricing in _PRICING_TABLE.items():
        if model.startswith(prefix):
            return pricing
    return None


def compute_evaluation_cost(
    usage: EvaluationTokenUsage,
    model: str,
    provider_name: str,
) -> EvaluationCost:
    """Compute estimated cost from accumulated token usage and a pricing table.

    Returns zero cost with a log warning for unknown models.
    """
    pricing = _find_pricing(model=model)
    if pricing is None:
        logger.warning(
            "No pricing data for model '%s', reporting zero cost",
            model,
        )
        return EvaluationCost(
            usage=usage,
            estimated_cost_usd=0.0,
            model=model,
            provider_name=provider_name,
        )

    cost = (
        usage.input_tokens * pricing.input_per_mtok
        + usage.output_tokens * pricing.output_per_mtok
        + usage.cache_read_input_tokens * pricing.cache_read_per_mtok
        + usage.cache_creation_input_tokens * pricing.cache_write_per_mtok
    ) / 1_000_000

    return EvaluationCost(
        usage=usage,
        estimated_cost_usd=cost,
        model=model,
        provider_name=provider_name,
    )
