"""Run a scenario's round loop, with only the model faked.

`assert_scenario_contract` proves a scenario builds: agents, channels, prompts,
consistent ids. It never starts the game clock, so nothing there notices if the
world's state machine, the postmortem phase, or the round verdict breaks. That
gap is what this closes. Everything except the LLM is real: MCP server, tool
dispatch, runtime, game clock, event logger, and the scenario's own world.

A test supplies its channel and a script, and asserts on the outcome. This
module owns the parts that would otherwise be written once per scenario.
"""

from pathlib import Path
from typing import Any

import pytest

from glossogen.scenario_loader import get_scenario_class
from glossogen.scenario_protocol import SimulationScenario
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import (
    SimulationResult,
    never_times_out,
    run_simulation,
)

DEFAULT_PRESET_NAME = "knobs_default"

# A round ends on idle only after MIN_ROUND_DURATION_SECONDS, so the wall-clock
# cap only has to be long enough not to fire first.
ROUND_SECONDS = 8.0
POSTMORTEM_SECONDS = 2.0


def build_scenario(scenario_name: str, overrides: dict[str, Any]) -> SimulationScenario:
    """Build ``scenario_name`` from its shipped default preset, plus overrides.

    Starting from the real preset rather than a hand-written config means a test
    exercises the configuration the scenario actually ships with, and a preset
    that drifted from its knobs model fails here too.

    The preset is read through the scenario class, so this resolves a scenario
    installed from another distribution as readily as a built-in one.
    """
    scenario_cls = get_scenario_class(name=scenario_name)
    config = dict(scenario_cls.load_knobs_preset(preset_name=DEFAULT_PRESET_NAME))
    config.update(overrides)
    prepared = scenario_cls.prepare_config(config=dict(config))
    return scenario_cls.create_from_config(config=dict(prepared))


def chat_script(channel_id: str, text: str) -> list[ScriptedTurn]:
    """Send one message, then fall silent so the round can end on idle.

    Deliberately no scenario-specific action tool. Those are judged by an LLM,
    and the point here is the round loop, not the verdict.
    """
    return [
        ToolTurn(
            tool_name="send_message",
            args={"channel_id": channel_id, "text": text, "force": True},
        ),
        SayTurn(text="done"),
    ]


def fast_round_overrides(round_count: int) -> dict[str, Any]:
    """The timing knobs that keep a scenario test to seconds rather than minutes.

    A scenario built without these runs its shipped preset, which is tens of
    rounds at minutes each. Any test that builds its own scenario and hands it
    to ``run_scenario`` needs them too.
    """
    return {
        "round_count": round_count,
        "max_round_duration_seconds": ROUND_SECONDS,
        "postmortem_duration_seconds": POSTMORTEM_SECONDS,
    }


async def run_rounds(
    scenario_name: str,
    round_count: int,
    overrides: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    """Run ``round_count`` rounds with every agent chatting once per round.

    Each agent is routed to whichever primary channel it belongs to, read from
    the scenario rather than hardcoded, so a two-team scenario sends on both
    team channels without the test naming either.
    """
    merged = fast_round_overrides(round_count=round_count)
    merged.update(overrides)
    scenario = build_scenario(scenario_name=scenario_name, overrides=merged)
    return await run_scenario(
        scenario=scenario, round_count=round_count, tmp_path=tmp_path, monkeypatch=monkeypatch
    )


async def run_scenario(
    scenario: SimulationScenario,
    round_count: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    """Run an already-built scenario, each agent chatting once per round.

    Taken separately from ``run_rounds`` so a test can reach the scenario before
    it runs, which is the only way to observe state that never reaches the event
    log.
    """
    agents = scenario.get_agents(default_model="m", default_provider="anthropic")
    primary_ids = [channel.channel_id for channel in scenario.get_primary_channels()]
    assert primary_ids, f"{scenario.name()} declares no primary channel to send on"

    scripts: dict[str, list[ScriptedTurn]] = {}
    for agent in agents:
        mine = [channel for channel in primary_ids if channel in agent.channel_ids]
        assert mine, f"{agent.agent_id} belongs to no primary channel of {primary_ids}"
        scripts[agent.agent_id] = (
            chat_script(channel_id=mine[0], text=f"{agent.agent_id} reporting") * round_count
        )
    return await run_simulation(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )


def primary_channel_ids_of(scenario_name: str) -> list[str]:
    """Return the channels the scenario's default preset scores."""
    scenario = build_scenario(scenario_name=scenario_name, overrides={})
    return [channel.channel_id for channel in scenario.get_primary_channels()]


def messages_on_primary(result: SimulationResult, scenario_name: str) -> int:
    """Count messages that landed on any primary channel."""
    return sum(
        len(result.messages_on(channel_id=channel_id))
        for channel_id in primary_channel_ids_of(scenario_name=scenario_name)
    )


def assert_round_loop_completed(result: SimulationResult, round_count: int) -> None:
    """Assert the clock drove every round to a recorded verdict and stopped.

    ``round_result_recorded`` is what the platform's ``round_success`` metric
    reads. A run that ends without one per round scores nothing, and reports a
    number rather than an error, so its absence has to fail here.
    """
    assert result.of_type(event_type="simulation_started"), "no simulation_started"
    assert result.of_type(event_type="simulation_ended"), "the run never ended cleanly"

    verdicts = result.of_type(event_type="round_result_recorded")
    rounds_judged = {verdict["round_number"] for verdict in verdicts}
    assert rounds_judged == set(
        range(1, round_count + 1)
    ), f"expected a verdict for rounds 1..{round_count}, got {sorted(rounds_judged)}"

    endings = result.of_type(event_type="round_ended")
    assert len(endings) == round_count, f"expected {round_count} round_ended, got {len(endings)}"


def assert_no_agent_crashed(result: SimulationResult) -> None:
    """Agents that die mid-cycle still let a run finish, with rounds nobody played."""
    failures = result.of_type(event_type="agent_run_cycle_failed")
    assert not failures, f"agent run cycles failed: {failures}"
    assert not result.failed_tool_calls(), f"tool calls failed: {result.failed_tool_calls()}"


def assert_postmortem_ran(result: SimulationResult, round_count: int) -> None:
    """A scenario with postmortem on must open and close the phase every round."""
    started = result.of_type(event_type="postmortem_started")
    ended = result.of_type(event_type="postmortem_ended")
    assert len(started) == round_count, f"expected {round_count} postmortems, got {len(started)}"
    assert len(ended) == len(started), "a postmortem opened without closing"


def assert_postmortem_never_ran(result: SimulationResult) -> None:
    """With postmortem off, the phase must not open at all.

    One scenario used to report a full-length postmortem duration for a run
    configured without one, because its copy of the check had lost a condition.
    """
    assert not result.of_type(event_type="postmortem_started"), "postmortem ran while disabled"
