"""Current hosted-model pricing registry checks."""

from glossogen.token_pricing import TokenPricing, find_pricing, list_models


def test_gpt_5_5_pricing_and_provider_are_registered() -> None:
    assert find_pricing("gpt-5.5") == TokenPricing(
        provider="openai",
        input_per_mtok=5.0,
        output_per_mtok=30.0,
        cache_read_per_mtok=0.50,
        cache_write_per_mtok=5.0,
    )
    assert ("gpt-5.5", "openai") in list_models()


def test_gpt_5_5_snapshot_uses_base_pricing() -> None:
    assert find_pricing("gpt-5.5-2026-04-23") == find_pricing("gpt-5.5")
