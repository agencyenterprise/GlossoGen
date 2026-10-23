"""Provider mappings passed to Pydantic AI."""

import pytest
from pydantic import ValidationError
from pydantic_ai.models import infer_model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.settings import ThinkingLevel

from glossogen.model_catalog import Provider
from glossogen.runners.pydantic_ai_model_factory import (
    agent_model_settings,
    build_pydantic_ai_model,
    default_pydantic_ai_settings,
    resolve_self_hosted_base_url,
)
from glossogen.scenarios.base_knobs import BaseKnobs


def test_google_gla_uses_pydantic_ais_google_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    model_name = build_pydantic_ai_model(
        model="gemini-2.5-flash",
        provider=Provider.GOOGLE_GLA,
    )
    assert model_name == "google:gemini-2.5-flash"
    assert isinstance(infer_model(model_name), GoogleModel)


@pytest.mark.parametrize(
    "mapping",
    ["[]", '{"model": null}', '{"model": ""}'],
)
def test_self_hosted_endpoint_map_must_contain_non_empty_urls(
    monkeypatch: pytest.MonkeyPatch,
    mapping: str,
) -> None:
    monkeypatch.setenv("SELF_HOSTED_BASE_URLS", mapping)
    with pytest.raises(ValueError, match="non-empty endpoint URLs"):
        resolve_self_hosted_base_url(model="model")


def test_agent_output_token_limit_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        BaseKnobs(
            round_count=1,
            max_round_duration_seconds=1,
            model_overrides={},
            agent_max_tokens=0,
        )


@pytest.mark.parametrize(
    ("model", "reasons"),
    [
        ("gpt-5.4", True),
        ("ft:o4-mini-2025-04-16:org:name:abc123", True),
        ("gpt-4.1-mini", False),
        ("ft:gpt-4.1-mini-2025-04-14:org:name:abc123", False),
    ],
)
def test_openai_reasoning_summary_goes_only_to_a_reasoning_model(model: str, reasons: bool) -> None:
    """A fine-tune is judged by its base model, the second field of its ``ft:`` name."""
    settings = default_pydantic_ai_settings(provider=Provider.OPENAI, model=model)

    assert ("openai_reasoning_summary" in settings) is reasons
    assert settings.get("max_tokens") == 32768


@pytest.mark.parametrize("provider", list(Provider))
def test_no_provider_is_sent_a_reasoning_effort_by_default(provider: Provider) -> None:
    """An OpenAI reasoning model used to get ``high`` whatever the run asked for."""
    settings = agent_model_settings(
        provider=provider, model="gpt-5.4", parallel_tool_calls=True, thinking=None
    )

    assert "thinking" not in settings
    assert "openai_reasoning_effort" not in settings
    assert "anthropic_thinking" not in settings
    assert "anthropic_effort" not in settings


@pytest.mark.parametrize("thinking", [True, False, "minimal", "low", "medium", "high", "xhigh"])
@pytest.mark.parametrize("provider", [Provider.ANTHROPIC, Provider.OPENAI, Provider.GOOGLE_GLA])
def test_a_thinking_level_goes_to_pydantic_ais_unified_field(
    provider: Provider, thinking: ThinkingLevel
) -> None:
    settings = agent_model_settings(
        provider=provider, model="gpt-5.4", parallel_tool_calls=True, thinking=thinking
    )

    assert settings.get("thinking") == thinking
    assert {key: value for key, value in settings.items() if key != "thinking"} == (
        default_pydantic_ai_settings(provider=provider, model="gpt-5.4")
    )


@pytest.mark.parametrize("value", ["max", "extreme", 3])
def test_the_knob_accepts_only_what_pydantic_ai_accepts(value: object) -> None:
    with pytest.raises(ValidationError):
        BaseKnobs.model_validate(
            {
                "round_count": 1,
                "max_round_duration_seconds": 1,
                "model_overrides": {},
                "agent_thinking": value,
            }
        )


@pytest.mark.parametrize("provider", [Provider.ANTHROPIC, Provider.OPENAI])
def test_a_scenario_can_ask_for_one_tool_call_per_response(provider: Provider) -> None:
    """pydantic-ai sends this to Anthropic as ``disable_parallel_tool_use`` and to
    OpenAI as ``parallel_tool_calls``; the provider defaults stay in place."""
    settings = agent_model_settings(
        provider=provider, model="m", parallel_tool_calls=False, thinking=None
    )

    assert settings.get("parallel_tool_calls") is False
    assert {
        key: value for key, value in settings.items() if key != "parallel_tool_calls"
    } == default_pydantic_ai_settings(provider=provider, model="m")


def test_allowing_parallel_tool_calls_leaves_the_provider_default_alone() -> None:
    settings = agent_model_settings(
        provider=Provider.ANTHROPIC, model="m", parallel_tool_calls=True, thinking=None
    )

    assert "parallel_tool_calls" not in settings
