"""Cost estimation for LLM evaluation calls."""

import logging
from datetime import UTC, datetime

from pydantic import BaseModel

from glossogen.models.agent_model_settings import JudgeModelSettings
from glossogen.token_pricing import compute_token_cost_usd, find_pricing

logger = logging.getLogger(__name__)


class EvaluationTokenUsage(BaseModel):
    """Accumulated token counts across all LLM calls during an evaluation run.

    ``input_tokens`` counts only the input that was neither read from nor written
    to the cache, the way the Anthropic API reports it.
    """

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


class EvaluationCost(BaseModel):
    """Token usage and estimated dollar cost for an evaluation run.

    ``model_settings`` are the settings the judge was sent with. ``None`` means
    they were not recorded: a report written before judges took settings, or a
    probe batch, whose agents each ran with their own.
    """

    usage: EvaluationTokenUsage
    estimated_cost_usd: float
    model: str
    provider_name: str
    model_settings: JudgeModelSettings | None = None


def compute_evaluation_cost(
    usage: EvaluationTokenUsage,
    model: str,
    provider_name: str,
    model_settings: JudgeModelSettings | None,
) -> EvaluationCost:
    """Compute estimated cost from accumulated token usage and a pricing table.

    Returns zero cost with a log warning for unknown models.
    """
    pricing = find_pricing(model=model, provider=provider_name, at=datetime.now(tz=UTC))
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
            model_settings=model_settings,
        )

    # compute_token_cost_usd takes an input count that includes the cached tokens.
    cost = compute_token_cost_usd(
        pricing=pricing,
        input_tokens=usage.input_tokens
        + usage.cache_read_input_tokens
        + usage.cache_creation_input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_input_tokens,
        cache_write_tokens=usage.cache_creation_input_tokens,
    )

    return EvaluationCost(
        usage=usage,
        estimated_cost_usd=cost,
        model=model,
        provider_name=provider_name,
        model_settings=model_settings,
    )
