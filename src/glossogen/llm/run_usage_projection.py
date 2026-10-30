"""Projects pydantic-ai's ``RunUsage`` onto the platform's token models."""

from pydantic_ai.usage import RunUsage

from glossogen.evaluation.reports.evaluation_cost import EvaluationTokenUsage
from glossogen.models.event_base import TokenUsage


def evaluation_token_usage(run_usage: RunUsage) -> EvaluationTokenUsage:
    """Return ``run_usage`` as an ``EvaluationTokenUsage``.

    ``RunUsage.input_tokens`` is the *total* prompt token count (non-cached +
    cache_read + cache_creation), which differs from the Anthropic API's
    ``input_tokens`` (after-breakpoint only). ``compute_evaluation_cost``
    expects ``EvaluationTokenUsage.input_tokens`` to be the non-cached
    portion only, so the cached counts are subtracted here.
    """
    non_cached_input = max(
        0,
        run_usage.input_tokens - run_usage.cache_read_tokens - run_usage.cache_write_tokens,
    )
    return EvaluationTokenUsage(
        input_tokens=non_cached_input,
        output_tokens=run_usage.output_tokens,
        cache_read_input_tokens=run_usage.cache_read_tokens,
        cache_creation_input_tokens=run_usage.cache_write_tokens,
    )


def simulation_token_usage(run_usage: RunUsage) -> TokenUsage:
    """Return ``run_usage`` as a ``TokenUsage`` for a simulation event.

    ``TokenUsage.input_tokens`` keeps pydantic-ai's convention, the total prompt
    count with the cached portions inside it, which is the opposite of what
    :func:`evaluation_token_usage` builds. ``reasoning_tokens`` is likewise the
    part of ``output_tokens`` spent thinking rather than an amount beyond it.
    """
    return TokenUsage(
        input_tokens=run_usage.input_tokens,
        output_tokens=run_usage.output_tokens,
        reasoning_tokens=run_usage.output_reasoning_tokens,
        cache_read_input_tokens=run_usage.cache_read_tokens,
        cache_creation_input_tokens=run_usage.cache_write_tokens,
    )
