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


def test_cross_model_validation_models_are_registered() -> None:
    expected = {
        "claude-opus-5": TokenPricing("anthropic", 5.0, 25.0, 0.50, 6.25),
        "claude-sonnet-5": TokenPricing("anthropic", 2.0, 10.0, 0.20, 2.50),
        "gpt-5.6-terra": TokenPricing("openai", 2.50, 15.0, 0.25, 3.125),
        "gpt-5.6-sol": TokenPricing("openai", 5.0, 30.0, 0.50, 6.25),
    }

    for model, pricing in expected.items():
        assert find_pricing(model) == pricing
        assert (model, pricing.provider) in list_models()
