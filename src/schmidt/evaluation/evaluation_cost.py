"""Cost estimation for LLM evaluation calls."""

import logging

from pydantic import BaseModel

from schmidt.token_pricing import find_pricing

logger = logging.getLogger(__name__)


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


def compute_evaluation_cost(
    usage: EvaluationTokenUsage,
    model: str,
    provider_name: str,
) -> EvaluationCost:
    """Compute estimated cost from accumulated token usage and a pricing table.

    Returns zero cost with a log warning for unknown models.
    """
    pricing = find_pricing(model=model)
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
