"""Token costs are priced from the genai-prices catalog.

The rates are resolved once per agent and applied with our own arithmetic, so
these tests hold that arithmetic to what genai-prices itself charges for a single
request below every long-context tier.
"""

from datetime import UTC, datetime

import pytest
from genai_prices import Usage, calc_price

from glossogen.evaluation.reports.evaluation_cost import (
    EvaluationTokenUsage,
    compute_evaluation_cost,
)
from glossogen.model_catalog import Provider, list_models
from glossogen.token_pricing import TokenPricing, compute_token_cost_usd, find_pricing

AT = datetime(2026, 10, 1, tzinfo=UTC)
HOSTED_MODELS = [pair for pair in list_models() if pair[1] != Provider.SELF_HOSTED]


def priced(model: str, provider: str) -> TokenPricing:
    pricing = find_pricing(model=model, provider=provider, at=AT)
    assert pricing is not None
    return pricing


def library_cost(model: str, provider: str, usage: Usage) -> float:
    calculation = calc_price(
        usage=usage, model_ref=model, provider_id=provider, genai_request_timestamp=AT
    )
    return float(calculation.total_price)


@pytest.mark.parametrize(("model", "provider"), HOSTED_MODELS)
def test_every_offered_model_costs_what_genai_prices_charges(model: str, provider: str) -> None:
    """Input counts include the cached tokens on both sides."""
    ours = compute_token_cost_usd(
        pricing=priced(model=model, provider=provider),
        input_tokens=50_000,
        output_tokens=2_000,
        cache_read_tokens=30_000,
        cache_write_tokens=5_000,
    )
    theirs = library_cost(
        model=model,
        provider=provider,
        usage=Usage(
            input_tokens=50_000,
            output_tokens=2_000,
            cache_read_tokens=30_000,
            cache_write_tokens=5_000,
        ),
    )
    assert ours == pytest.approx(theirs, rel=1e-9)


def test_a_dotted_model_name_prices_like_the_dashed_one() -> None:
    assert priced(model="claude-haiku-4.5", provider="anthropic") == priced(
        model="claude-haiku-4-5-20251001", provider="anthropic"
    )


def test_a_tiered_rate_is_taken_at_its_base_tier() -> None:
    """A million input tokens summed over many requests is not one long-context request."""
    pricing = priced(model="gpt-5.4", provider="openai")
    summed = compute_token_cost_usd(
        pricing=pricing,
        input_tokens=1_000_000,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
    )
    one_small_request = library_cost(
        model="gpt-5.4", provider="openai", usage=Usage(input_tokens=1_000, output_tokens=0)
    )
    assert summed == pytest.approx(one_small_request * 1_000, rel=1e-9)


def test_a_model_without_a_cache_write_rate_bills_cache_writes_as_input() -> None:
    pricing = priced(model="gpt-5.4-mini", provider="openai")
    assert pricing.cache_write_per_mtok == pricing.input_per_mtok


def test_a_self_hosted_model_costs_nothing() -> None:
    pricing = find_pricing(
        model="meta-llama/Llama-3.3-70B-Instruct", provider=Provider.SELF_HOSTED, at=AT
    )
    assert pricing == TokenPricing(
        input_per_mtok=0.0,
        output_per_mtok=0.0,
        cache_read_per_mtok=0.0,
        cache_write_per_mtok=0.0,
    )


@pytest.mark.parametrize(
    ("model", "provider"),
    [
        ("claude-does-not-exist-9", "anthropic"),
        ("gpt-5.4", "anthropic"),
        ("scripted::sender", "scripted"),
    ],
)
def test_a_model_the_catalog_does_not_know_is_not_priced(model: str, provider: str) -> None:
    assert find_pricing(model=model, provider=provider, at=AT) is None


def test_a_locally_served_model_is_priced_at_zero() -> None:
    """Ollama serves from the operator's own hardware, like a self-hosted endpoint."""
    pricing = find_pricing(model="llama3.3", provider=Provider.OLLAMA, at=AT)
    assert pricing is not None
    assert pricing.input_per_mtok == 0.0
    assert pricing.output_per_mtok == 0.0


def test_evaluation_input_counts_exclude_the_cached_tokens() -> None:
    """`EvaluationTokenUsage.input_tokens` follows the Anthropic API: cached tokens are apart."""
    cost = compute_evaluation_cost(
        usage=EvaluationTokenUsage(
            input_tokens=10_000,
            output_tokens=1_000,
            cache_read_input_tokens=40_000,
            cache_creation_input_tokens=5_000,
        ),
        model="claude-haiku-4-5-20251001",
        provider_name="anthropic",
    )
    theirs = library_cost(
        model="claude-haiku-4-5-20251001",
        provider="anthropic",
        usage=Usage(
            input_tokens=55_000,
            output_tokens=1_000,
            cache_read_tokens=40_000,
            cache_write_tokens=5_000,
        ),
    )
    assert cost.estimated_cost_usd == pytest.approx(theirs, rel=1e-9)
    assert theirs > 0
