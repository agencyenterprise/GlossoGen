"""Scripted turns and a runner for move_a_box round-loop tests."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B
from glossogen.scenarios.move_a_box.scenario import MoveABoxScenario
from glossogen.testing.scenario_runtime import assert_no_agent_crashed, build_scenario
from glossogen.testing.scripted_agent import ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult, never_times_out, run_simulation

ONE_ROUND: dict[str, Any] = {
    "round_count": 1,
    "crate_start": "corner",
    "pallet_density": 0.0,
}
"""Round 1 under seed 42 on the default preset, over a clear floor from the corner.

The route constants below are fixed paths from row 1, col 1, so these tests state
the geometry they walk instead of taking whichever one the preset ships: a pallet
in the way would turn a scripted haul into a refusal. Bay 5 stands at row 6, col 3
and is the only bay the depot assigns to both: operator_a also gets bays 2 and 4,
operator_b bays 1 and 3.
"""

CRATE_A = f"{OPERATOR_A}#1"
CRATE_B = f"{OPERATOR_B}#1"
"""The one crate each operator works under ``ONE_ROUND``, which sets crates_each to 1."""

SHARED_BAY = 5
"""The bay round 1 assigns to both operators."""

TO_SHARED_BAY = ["right", "right", "down", "down", "down", "down", "down"]
"""The hauls from the start square to bay 5, at row 6, col 3."""

TO_BAY_FOUR = ["right", "right", "right", "down", "down", "down", "down"]
"""The hauls to bay 4, at row 5, col 4. The depot assigns it to operator_a alone."""

TO_BAY_THREE = ["down", "down", "down", "down"]
"""The hauls to bay 3, at row 5, col 1. The depot assigns it to operator_b alone."""

TO_BAY_ONE = ["right", "down", "down"]
"""The hauls to bay 1, at row 3, col 2. The depot assigns it to operator_b alone."""


def build(preset_name: str, overrides: dict[str, Any]) -> MoveABoxScenario:
    scenario = build_scenario(
        scenario_name="move_a_box", preset_name=preset_name, overrides=overrides
    )
    assert isinstance(scenario, MoveABoxScenario)
    return scenario


def read() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={})


def wait_for_next_round() -> ToolTurn:
    return ToolTurn(tool_name="read_notifications", args={"wait_for": "next_round"})


def act(steps: list[tuple[str, str | None]]) -> ToolTurn:
    """One act call, each step an action and the direction it takes, or None."""
    return ToolTurn(
        tool_name="act",
        args={
            "steps": [{"action": action, "direction": direction} for action, direction in steps],
            "reasoning": "Scripted actions.",
        },
    )


def haul(method: str, direction: str) -> ToolTurn:
    return act(steps=[(method, direction)])


def stand_by() -> ToolTurn:
    return act(steps=[("stand_by", None)])


def pack_ice() -> ToolTurn:
    return act(steps=[("pack_ice", None)])


def finish() -> ToolTurn:
    return act(steps=[("finish", None)])


def notepad(text: str) -> ToolTurn:
    return ToolTurn(tool_name="notepad", args={"text": text})


def haul_path(directions: list[str], method: str) -> list[ToolTurn]:
    """One act call per direction, all carried the same way."""
    return [haul(method=method, direction=direction) for direction in directions]


def haul_burst(directions: list[str], method: str) -> ToolTurn:
    """One act call that carries the crate the whole way, all by the same method."""
    return act(steps=[(method, direction) for direction in directions])


def to_shared_bay(method: str) -> list[ToolTurn]:
    """The hauls that put a crate on the bay both operators were assigned."""
    return haul_path(directions=TO_SHARED_BAY, method=method)


async def play(
    scenario: MoveABoxScenario,
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
