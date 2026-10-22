"""Scripted turns and a runner for signal_game_server round-loop tests."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from glossogen.models.event import ToolResultReceived
from glossogen.scenarios.signal_game_server.events import SignalGameServerRoundResolved
from glossogen.scenarios.signal_game_server.scenario import SignalGameServerScenario
from glossogen.testing.scenario_runtime import assert_no_agent_crashed, build_scenario
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation

ONE_ROUND: dict[str, Any] = {"round_count": 1}
"""Round 1 under seed 42: player_a's grid is red red / green blue, player_b's is
blue blue / red red, and both fall back to row 2, col 2 (player_a on blue, player_b on
red)."""


def build(overrides: dict[str, Any]) -> SignalGameServerScenario:
    scenario = build_scenario(
        scenario_name="signal_game_server", preset_name="knobs_default", overrides=overrides
    )
    assert isinstance(scenario, SignalGameServerScenario)
    return scenario


def read() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={})


def wait_for_next_round() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={"wait_for": "next_round"})


def end_round_on(row: int, col: int) -> ToolTurn:
    return ToolTurn(
        tool_name="end_round", args={"row": row, "col": col, "reasoning": "Scripted end."}
    )


async def play(
    scenario: SignalGameServerScenario,
    scripts: dict[str, list[ScriptedTurn]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> SimulationResult:
    async with asyncio.timeout(60):
        result = await run_simulation(
            scenario=scenario,
            scripts=scripts,
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
            phase_timed_out=never_times_out,
        )
    assert_no_agent_crashed(result=result)
    return result


def resolved(result: SimulationResult) -> SignalGameServerRoundResolved:
    """The run's one resolved round."""
    [outcome] = result.of_type(event_type=SignalGameServerRoundResolved)
    return outcome


def results_for(result: SimulationResult, agent_id: str, tool_name: str) -> list[str]:
    """Every result ``agent_id`` read from ``tool_name``, in order."""
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == tool_name
    ]
