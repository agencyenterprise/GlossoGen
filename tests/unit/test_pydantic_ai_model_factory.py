"""Provider mappings passed to Pydantic AI."""

import pytest
from pydantic import ValidationError
from pydantic_ai.models import infer_model
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.settings import ModelSettings, ThinkingLevel

from glossogen.evaluation.metrics.protocol_probe.probe_agent import (
    _probe_model_settings,  # pyright: ignore[reportPrivateUsage]
)
from glossogen.model_catalog import Provider
from glossogen.models.agent_model_settings import AgentModelSettings
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


def knobs(**fields: object) -> BaseKnobs:
    return BaseKnobs.model_validate(
        {"round_count": 1, "max_round_duration_seconds": 1, "model_overrides": {}, **fields}
    )


def test_agent_output_token_limit_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        knobs(agent_model_settings={"max_tokens": 0})


def test_a_config_written_before_the_settings_object_keeps_its_output_cap() -> None:
    """Shipped presets and every older run's recorded config spell it ``agent_max_tokens``."""
    assert knobs(agent_max_tokens=2048).agent_model_settings == AgentModelSettings(max_tokens=2048)


def test_a_fork_adding_a_thinking_level_keeps_the_sources_old_output_cap() -> None:
    """A fork merges the caller's knobs over the source's recorded config, key by key."""
    merged = knobs(agent_max_tokens=2048, agent_model_settings={"thinking": "high"})

    assert merged.agent_model_settings == AgentModelSettings(max_tokens=2048, thinking="high")


def test_the_settings_objects_own_output_cap_wins_over_the_old_name() -> None:
    merged = knobs(agent_max_tokens=2048, agent_model_settings={"max_tokens": 4096})

    assert merged.agent_model_settings.max_tokens == 4096


def test_every_setting_is_named_as_pydantic_ai_names_it() -> None:
    """``to_pydantic_ai`` is a plain dump, so a misnamed field would be sent nowhere."""
    assert set(AgentModelSettings.model_fields) <= set(ModelSettings.__annotations__)


def test_every_setting_set_reaches_pydantic_ai() -> None:
    settings = AgentModelSettings(
        max_tokens=512,
        thinking="low",
        temperature=0.2,
        top_p=0.9,
        top_k=40,
        seed=42,
        presence_penalty=0.1,
        frequency_penalty=0.3,
        logit_bias={"50256": -100},
        stop_sequences=["END"],
        service_tier="flex",
        timeout=30,
        parallel_tool_calls=True,
        extra_body={"reasoning": {"exclude": True}},
    )

    assert settings.to_pydantic_ai() == {
        "max_tokens": 512,
        "thinking": "low",
        "temperature": 0.2,
        "top_p": 0.9,
        "top_k": 40,
        "seed": 42,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.3,
        "logit_bias": {"50256": -100},
        "stop_sequences": ["END"],
        "service_tier": "flex",
        "timeout": 30,
        "parallel_tool_calls": True,
        "extra_body": {"reasoning": {"exclude": True}},
    }


def test_a_setting_left_unset_is_not_sent() -> None:
    assert AgentModelSettings().to_pydantic_ai() == {"max_tokens": 16384}


@pytest.mark.parametrize(
    "settings",
    [
        {"timeout": 0},
        {"service_tier": "fastest"},
        {"extra_body": "not an object"},
        {"tool_choice": "none"},
        {"extra_headers": {"Authorization": "Bearer x"}},
    ],
)
def test_a_setting_outside_the_supported_ones_is_refused(settings: dict[str, object]) -> None:
    """``tool_choice`` and ``extra_headers`` are pydantic-ai settings the knob leaves out."""
    with pytest.raises(ValidationError):
        knobs(agent_model_settings=settings)


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


@pytest.mark.parametrize("provider", list(Provider))
def test_no_provider_default_caps_the_output(provider: Provider) -> None:
    """Agents send their own cap; a judge or a probe without one gets the provider's."""
    settings = default_pydantic_ai_settings(provider=provider, model="gpt-5.4")

    assert "max_tokens" not in settings


@pytest.mark.parametrize("provider", [Provider.ANTHROPIC, Provider.OPENAI])
def test_a_probe_drops_the_agents_cap_and_keeps_its_other_settings(provider: Provider) -> None:
    """An agent's cap is sized for tool calls; a probe answers in structured output."""
    settings = _probe_model_settings(
        provider=provider,
        model="gpt-5.4",
        model_settings=AgentModelSettings(max_tokens=2048, thinking="low"),
    )

    assert "max_tokens" not in settings
    assert settings.get("thinking") == "low"


@pytest.mark.parametrize("provider", list(Provider))
def test_no_provider_is_sent_a_reasoning_effort_by_default(provider: Provider) -> None:
    """An OpenAI reasoning model used to get ``high`` whatever the run asked for."""
    settings = agent_model_settings(
        provider=provider, model="gpt-5.4", settings=AgentModelSettings()
    )

    assert "thinking" not in settings
    assert "openai_reasoning_effort" not in settings
    assert "anthropic_thinking" not in settings
    assert "anthropic_effort" not in settings


@pytest.mark.parametrize("thinking", [True, False, "minimal", "low", "medium", "high", "xhigh"])
@pytest.mark.parametrize("provider", [Provider.ANTHROPIC, Provider.OPENAI, Provider.GOOGLE_GLA])
def test_the_agents_settings_win_over_the_provider_defaults(
    provider: Provider, thinking: ThinkingLevel
) -> None:
    settings = agent_model_settings(
        provider=provider,
        model="gpt-5.4",
        settings=AgentModelSettings(max_tokens=2048, thinking=thinking),
    )

    assert settings == {
        **default_pydantic_ai_settings(provider=provider, model="gpt-5.4"),
        "max_tokens": 2048,
        "thinking": thinking,
    }


@pytest.mark.parametrize("value", ["max", "extreme", 3])
def test_the_thinking_level_accepts_only_what_pydantic_ai_accepts(value: object) -> None:
    with pytest.raises(ValidationError):
        knobs(agent_model_settings={"thinking": value})


@pytest.mark.parametrize("provider", [Provider.ANTHROPIC, Provider.OPENAI])
def test_one_tool_call_per_response_can_be_asked_for(provider: Provider) -> None:
    """pydantic-ai sends this to Anthropic as ``disable_parallel_tool_use`` and to
    OpenAI as ``parallel_tool_calls``; the other settings stay in place."""
    settings = agent_model_settings(
        provider=provider, model="m", settings=AgentModelSettings(parallel_tool_calls=False)
    )

    assert settings == {
        **default_pydantic_ai_settings(provider=provider, model="m"),
        "max_tokens": 16384,
        "parallel_tool_calls": False,
    }
