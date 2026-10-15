"""Scripted turns and a runner for signal_game round-loop tests."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from glossogen.scenarios.signal_game.scenario import SignalGameScenario
from glossogen.testing.scenario_runtime import assert_no_agent_crashed, build_scenario
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation

ONE_ROUND: dict[str, Any] = {"round_count": 1}
"""Round 1 under seed 42: player_a's grid is red red / green blue, player_b's is
blue blue / red red."""


def build(preset_name: str, overrides: dict[str, Any]) -> SignalGameScenario:
    scenario = build_scenario(
        scenario_name="signal_game", preset_name=preset_name, overrides=overrides
    )
    assert isinstance(scenario, SignalGameScenario)
    return scenario


def read() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={})


def finish() -> ToolTurn:
    """Finish the round on the current square and wait for the next briefing."""
    return ToolTurn(tool_name="read_notifications", args={"wait_for": "next_round"})


def move(directions: list[str]) -> ToolTurn:
    return ToolTurn(tool_name="move", args={"directions": directions})


async def play(
    scenario: SignalGameScenario,
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
