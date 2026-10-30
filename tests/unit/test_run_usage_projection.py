"""Covers the projections from pydantic-ai's ``RunUsage`` onto the token models."""

from pydantic_ai.usage import RunUsage

from glossogen.llm.run_usage_projection import evaluation_token_usage, simulation_token_usage


def test_reasoning_tokens_reach_the_simulation_event() -> None:
    """The thinking a reasoning model does is what the run log is missing without this."""
    usage = simulation_token_usage(
        run_usage=RunUsage(
            input_tokens=1_000,
            output_tokens=900,
            output_reasoning_tokens=750,
            cache_read_tokens=800,
            cache_write_tokens=50,
        )
    )

    assert usage.reasoning_tokens == 750


def test_reasoning_tokens_are_part_of_the_output_count_not_an_addition() -> None:
    """Anything summing these counts reads output_tokens alone, or charges thinking twice."""
    usage = simulation_token_usage(
        run_usage=RunUsage(input_tokens=1_000, output_tokens=900, output_reasoning_tokens=750)
    )

    assert usage.output_tokens == 900
    assert usage.reasoning_tokens < usage.output_tokens


def test_a_model_that_reports_no_reasoning_leaves_the_count_at_zero() -> None:
    """A provider without a reasoning breakdown reads the same as one that did not think."""
    usage = simulation_token_usage(run_usage=RunUsage(input_tokens=1_000, output_tokens=900))

    assert usage.reasoning_tokens == 0


def test_the_simulation_input_count_keeps_the_cached_tokens_inside_it() -> None:
    """The two projections take opposite conventions, so the split is worth pinning."""
    run_usage = RunUsage(
        input_tokens=1_000, output_tokens=900, cache_read_tokens=800, cache_write_tokens=50
    )

    assert simulation_token_usage(run_usage=run_usage).input_tokens == 1_000
    assert evaluation_token_usage(run_usage=run_usage).input_tokens == 150
