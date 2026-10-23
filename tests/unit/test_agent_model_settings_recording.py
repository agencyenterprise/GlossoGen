"""What the log records of each agent's model settings, and how it is read back.

A registration line logged before ``model_settings`` existed carries only
``max_tokens``. It is read into the settings object with nothing else set, since
nothing else was recorded.
"""

from typing import Any

from glossogen.evaluation.log_reader import extract_agent_configs
from glossogen.evaluation.metric_core.mid_run_swap_overrides import apply_mid_run_swaps
from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import AgentRegistered, AgentSwappedMidRun, SimulationEvent


def registration_line() -> dict[str, Any]:
    """An ``agent_registered`` line as a log recorded before ``model_settings`` holds it."""
    return {
        "event_type": "agent_registered",
        "agent_id": "observer",
        "role_name": "Observer",
        "system_prompt": "You observe.",
        "channel_ids": ["link"],
        "tool_names": ["send_message"],
        "model": "gpt-5.4",
        "provider": "openai",
        "max_tokens": 2048,
        "round_number": 0,
    }


def registration_with(settings: AgentModelSettings) -> AgentRegistered:
    line = registration_line()
    del line["max_tokens"]
    line["model_settings"] = settings.model_dump(mode="json")
    return AgentRegistered.model_validate(line)


def test_a_legacy_line_is_read_into_the_settings_object() -> None:
    registration = AgentRegistered.model_validate(registration_line())

    assert registration.model_settings == AgentModelSettings(max_tokens=2048)


def test_a_registration_logged_now_round_trips() -> None:
    settings = AgentModelSettings(max_tokens=4096, thinking="medium")
    written = registration_with(settings=settings).model_dump(mode="json")

    assert "max_tokens" not in written
    assert AgentRegistered.model_validate(written).model_settings == settings


def test_configs_rebuilt_for_the_probes_carry_the_recorded_settings() -> None:
    """The probes ask each agent under its own model, and with its own settings."""
    settings = AgentModelSettings(max_tokens=4096, thinking="high")
    events: list[SimulationEvent] = [registration_with(settings=settings)]

    [config] = extract_agent_configs(events=events)

    assert config.model_settings == settings


def test_a_swapped_in_agent_is_probed_with_its_own_settings() -> None:
    swap = AgentSwappedMidRun(
        agent_id="observer",
        new_model="claude-sonnet-4-6",
        new_provider="anthropic",
        channel_visibility={},
        model_settings=AgentModelSettings(max_tokens=1024, thinking="low"),
        round_number=3,
    )
    events: list[SimulationEvent] = [
        registration_with(settings=AgentModelSettings(thinking="xhigh")),
        swap,
    ]

    [config] = apply_mid_run_swaps(
        agent_configs=extract_agent_configs(events=events), events=events
    )

    assert (config.model, config.model_settings) == (
        "claude-sonnet-4-6",
        AgentModelSettings(max_tokens=1024, thinking="low"),
    )


def test_a_swap_logged_before_settings_were_recorded_keeps_its_predecessors() -> None:
    swap = AgentSwappedMidRun(
        agent_id="observer",
        new_model="claude-sonnet-4-6",
        new_provider="anthropic",
        channel_visibility={},
        round_number=3,
    )
    events: list[SimulationEvent] = [AgentRegistered.model_validate(registration_line()), swap]

    [config] = apply_mid_run_swaps(
        agent_configs=extract_agent_configs(events=events), events=events
    )

    assert config.model_settings == AgentModelSettings(max_tokens=2048)
