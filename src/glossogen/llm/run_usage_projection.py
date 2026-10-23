"""Projects pydantic-ai's ``RunUsage`` onto the evaluation cost token model."""

from pydantic_ai.usage import RunUsage

from glossogen.evaluation.reports.evaluation_cost import EvaluationTokenUsage


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
