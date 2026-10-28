"""Tests for an agent's own ``model_settings`` in its ``model_overrides`` entry.

Covers which settings an agent sends (``BaseKnobs.model_settings_for``), that a
config records an override's settings through normalization, and that a fork
keeps them for the agents it does not replace.
"""

import pytest

from glossogen.model_catalog import Provider
from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import AgentRegistered
from glossogen.run_config.config_overrides import (
    ResolvedAgentModel,
    model_overrides_config_value,
    normalize_agent_overrides,
)
from glossogen.run_derivation.replace_agent import (
    build_model_overrides,
    read_replacement_settings,
    read_user_model_overrides,
)
from glossogen.scenarios.base_knobs import AgentModelOverride, BaseKnobs

QWEN = "Qwen/Qwen3.8-27B"
RUN_SETTINGS = AgentModelSettings(max_tokens=16384, thinking="medium")
QWEN_SETTINGS = AgentModelSettings(
    max_tokens=16384,
    temperature=0.7,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)


def knobs_with(model_overrides: dict[str, AgentModelOverride]) -> BaseKnobs:
    """Knobs whose run settings are ``RUN_SETTINGS``, with ``model_overrides`` as given."""
    return BaseKnobs(
        round_count=1,
        max_round_duration_seconds=60,
        model_overrides=model_overrides,
        agent_model_settings=RUN_SETTINGS,
    )


def test_an_agent_with_its_own_settings_sends_them() -> None:
    """An agent whose override names settings sends them; one with no override sends the run's."""
    knobs = knobs_with(
        model_overrides={
            "viewer_2": AgentModelOverride(
                model=QWEN, provider=Provider.SELF_HOSTED, model_settings=QWEN_SETTINGS
            )
        }
    )

    assert knobs.model_settings_for(agent_id="viewer_2") == QWEN_SETTINGS
    assert knobs.model_settings_for(agent_id="viewer_1") == RUN_SETTINGS


def test_an_override_without_settings_sends_the_runs() -> None:
    """An override that only moves an agent to another model keeps the run's settings."""
    knobs = knobs_with(
        model_overrides={"viewer_2": AgentModelOverride(model="gpt-6.1-sol", provider=None)}
    )

    assert knobs.model_settings_for(agent_id="viewer_2") == RUN_SETTINGS


def test_a_config_records_an_overrides_settings_and_omits_them_when_unset() -> None:
    """Normalization keeps an override's settings, and a config records them only when set."""
    normalized = normalize_agent_overrides(
        agent_overrides={
            "viewer_2": {
                "model": QWEN,
                "provider": "self-hosted",
                "model_settings": QWEN_SETTINGS.model_dump(mode="json"),
            },
            "viewer_1": {"model": "gpt-6.1-sol"},
        },
        default_provider="openai",
        valid_providers=set(Provider),
    )

    assert normalized["viewer_2"].model_settings == QWEN_SETTINGS
    recorded = model_overrides_config_value(overrides=normalized)
    assert recorded["viewer_2"]["model_settings"] == QWEN_SETTINGS.model_dump(mode="json")
    assert recorded["viewer_1"] == {"model": "gpt-6.1-sol", "provider": "openai"}


def registration(agent_id: str, model: str, provider: Provider) -> AgentRegistered:
    """A source run's registration of ``agent_id`` on ``model``, sending the run's settings."""
    return AgentRegistered(
        agent_id=agent_id,
        role_name=agent_id,
        system_prompt="",
        channel_ids=[],
        tool_names=[],
        model=model,
        provider=provider.value,
        model_settings=RUN_SETTINGS,
        round_number=0,
    )


def test_a_fork_keeps_an_agents_own_settings_and_the_replaced_agent_sends_the_runs() -> None:
    """A fork reads seat settings from the merged ``model_overrides``; a replaced seat gets none."""
    source_agents = {
        "viewer_1": registration(
            agent_id="viewer_1", model="gpt-6.1-sol", provider=Provider.OPENAI
        ),
        "viewer_2": registration(agent_id="viewer_2", model=QWEN, provider=Provider.SELF_HOSTED),
        "viewer_3": registration(agent_id="viewer_3", model=QWEN, provider=Provider.SELF_HOSTED),
    }
    qwen_entry = {
        "model": QWEN,
        "provider": "self-hosted",
        "model_settings": QWEN_SETTINGS.model_dump(mode="json"),
    }
    user_overrides = read_user_model_overrides(
        merged_scenario_config={"model_overrides": {"viewer_2": qwen_entry, "viewer_3": qwen_entry}}
    )

    overrides = build_model_overrides(
        source_agents=source_agents,
        replaced_agent_id="viewer_3",
        replacement_model="claude-opus-5-5",
        replacement_provider="anthropic",
        replacement_settings=read_replacement_settings(
            knobs=None,
            replaced_agent_id="viewer_3",
            replacement_model="claude-opus-5-5",
            replacement_provider="anthropic",
        ),
        user_overrides=user_overrides,
    )

    assert overrides["viewer_2"].model_settings == QWEN_SETTINGS
    assert overrides["viewer_3"] == ResolvedAgentModel(
        model="claude-opus-5-5", provider=Provider.ANTHROPIC, model_settings=None
    )
    assert overrides["viewer_1"].model_settings is None


def test_a_replaced_agent_sends_the_settings_the_callers_knobs_name_for_it() -> None:
    """The caller's ``--knobs`` entry for the replaced seat gives the replacement its settings."""
    opus_settings = AgentModelSettings(max_tokens=8192, thinking="low")
    knobs = {
        "model_overrides": {
            "viewer_2": {
                "model": "claude-opus-5-5",
                "provider": "anthropic",
                "model_settings": opus_settings.model_dump(mode="json"),
            }
        }
    }

    overrides = build_model_overrides(
        source_agents={
            "viewer_1": registration(
                agent_id="viewer_1", model="gpt-6.1-sol", provider=Provider.OPENAI
            ),
            "viewer_2": registration(
                agent_id="viewer_2", model=QWEN, provider=Provider.SELF_HOSTED
            ),
        },
        replaced_agent_id="viewer_2",
        replacement_model="claude-opus-5-5",
        replacement_provider="anthropic",
        replacement_settings=read_replacement_settings(
            knobs=knobs,
            replaced_agent_id="viewer_2",
            replacement_model="claude-opus-5-5",
            replacement_provider="anthropic",
        ),
        user_overrides=read_user_model_overrides(merged_scenario_config=knobs),
    )

    assert overrides["viewer_2"] == ResolvedAgentModel(
        model="claude-opus-5-5", provider=Provider.ANTHROPIC, model_settings=opus_settings
    )
    assert overrides["viewer_1"].model_settings is None


def test_a_knobs_entry_for_the_replaced_seat_must_name_the_commands_model_and_provider() -> None:
    """An entry naming another pair is refused: the command's pair is what the seat runs under."""
    knobs = {
        "model_overrides": {
            "viewer_2": {
                "model": "claude-sonnet-5-5",
                "provider": "anthropic",
                "model_settings": {"thinking": "low"},
            }
        }
    }

    with pytest.raises(ValueError, match="names 'claude-sonnet-5-5' on 'anthropic'"):
        read_replacement_settings(
            knobs=knobs,
            replaced_agent_id="viewer_2",
            replacement_model="claude-opus-5-5",
            replacement_provider="anthropic",
        )


def test_a_knobs_entry_for_the_replaced_seat_must_name_a_provider() -> None:
    """An entry with no provider is refused as one, before its pair is compared."""
    knobs = {
        "model_overrides": {
            "viewer_2": {"model": "claude-opus-5-5", "model_settings": {"thinking": "low"}}
        }
    }

    with pytest.raises(ValueError, match=r"model_overrides\['viewer_2'\] must name a provider"):
        read_replacement_settings(
            knobs=knobs,
            replaced_agent_id="viewer_2",
            replacement_model="claude-opus-5-5",
            replacement_provider="anthropic",
        )
