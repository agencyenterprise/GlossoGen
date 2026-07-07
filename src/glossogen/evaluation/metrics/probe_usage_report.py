"""Per-(model, provider) LLM usage aggregation shared by the probe-style metrics.

Both ``protocol_probe`` and ``protocol_explanation`` issue one structured LLM
call per agent (probed under that agent's own model) and need to roll the
resulting token usage up into a per-(model, provider) cost report written
alongside the run. This module owns that accumulation so neither metric
duplicates it.
"""

from pydantic import BaseModel

from glossogen.evaluation.reports.evaluation_cost import (
    EvaluationCost,
    EvaluationTokenUsage,
    compute_evaluation_cost,
)


class ProbeUsageReport(BaseModel):
    """Aggregated probe LLM usage and cost across one evaluation run.

    ``per_model`` lists one entry per distinct ``(model, provider)`` pair
    encountered during the run; the list typically has one entry in
    single-team runs and may have more in cross-team or replace-agent runs
    where agents use different models.
    """

    total_estimated_cost_usd: float
    per_model: list[EvaluationCost]


def accumulate_probe_usage(
    usage_by_model: dict[tuple[str, str], EvaluationTokenUsage],
    model: str,
    provider: str,
    call_usage: EvaluationTokenUsage,
) -> None:
    """Increment the per-(model, provider) running totals by one probe call's usage."""
    key = (model, provider)
    existing = usage_by_model.get(key)
    if existing is None:
        usage_by_model[key] = call_usage
        return
    usage_by_model[key] = EvaluationTokenUsage(
        input_tokens=existing.input_tokens + call_usage.input_tokens,
        output_tokens=existing.output_tokens + call_usage.output_tokens,
        cache_read_input_tokens=existing.cache_read_input_tokens
        + call_usage.cache_read_input_tokens,
        cache_creation_input_tokens=existing.cache_creation_input_tokens
        + call_usage.cache_creation_input_tokens,
    )


def build_probe_usage_report(
    usage_by_model: dict[tuple[str, str], EvaluationTokenUsage],
) -> ProbeUsageReport:
    """Compute per-model cost and aggregate the run total."""
    per_model = [
        compute_evaluation_cost(usage=usage, model=model, provider_name=provider)
        for (model, provider), usage in usage_by_model.items()
    ]
    total = sum(entry.estimated_cost_usd for entry in per_model)
    return ProbeUsageReport(
        total_estimated_cost_usd=total,
        per_model=per_model,
    )
