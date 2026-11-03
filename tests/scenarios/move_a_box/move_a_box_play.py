"""Scripted turns and a runner for move_a_box round-loop tests."""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from glossogen.scenarios.move_a_box.depot import (
    Cell,
    RoundDepot,
    TargetLayout,
    draw_next_target,
    generate_depots,
)
from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B, operator_ids
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

TWO_TARGETS: dict[str, Any] = {**ONE_ROUND, "targets_per_round": 2}
"""One round of two targets, from the corner over a clear floor."""

OPERATORS = (OPERATOR_A, OPERATOR_B)

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


CORNER = Cell(row=1, col=1)


def route_between(start: Cell, end: Cell) -> list[str]:
    """The hauls from ``start`` to ``end`` on a clear floor: rows first, then columns."""
    rows = end.row - start.row
    cols = end.col - start.col
    vertical = ["down"] * rows
    if rows < 0:
        vertical = ["up"] * -rows
    horizontal = ["right"] * cols
    if cols < 0:
        horizontal = ["left"] * -cols
    return vertical + horizontal


def first_depot(scenario: MoveABoxScenario) -> RoundDepot:
    """Round 1's floor, drawn from the scenario's knobs the way the scenario draws it.

    The marked-bay tests read their routes off it, because under symbol or
    letter bays each floor's squares are its own and no constant route reaches
    the shared bay on both.
    """
    knobs = scenario.get_knobs()
    [depot] = generate_depots(
        seed=knobs.seed,
        agent_ids=operator_ids(operator_count=knobs.operator_count),
        bay_identities=(knobs.bay_identity_of(round_number=1),),
        grid_size=knobs.grid_size,
        bay_count=knobs.bay_count,
        bays_allowed_each=knobs.bays_allowed_each,
        crates_each=knobs.crates_each,
        bays_differ=knobs.bays_differ,
        crate_start=knobs.crate_start,
        pallet_density=knobs.pallet_density,
    )
    return depot


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


def haul(method: str, direction: str) -> ToolTurn:
    return ToolTurn(
        tool_name="haul",
        args={"method": method, "direction": direction, "reasoning": "Scripted haul."},
    )


def stand_by() -> ToolTurn:
    return ToolTurn(tool_name="stand_by", args={"reasoning": "Scripted stand by."})


def pack_ice() -> ToolTurn:
    return ToolTurn(tool_name="pack_ice", args={"reasoning": "Scripted ice."})


def finish() -> ToolTurn:
    return ToolTurn(tool_name="finish", args={"reasoning": "Scripted finish."})


def notepad(text: str) -> ToolTurn:
    return ToolTurn(tool_name="notepad", args={"text": text})


def haul_path(directions: list[str], method: str) -> list[ToolTurn]:
    """One haul per direction, all carried the same way."""
    return [haul(method=method, direction=direction) for direction in directions]


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


def bay_cell(target: TargetLayout, agent_id: str, shared: bool) -> Cell:
    """The square of the bay on ``agent_id``'s list that is, or is not, on the other list too."""
    [other] = [operator for operator in OPERATORS if operator != agent_id]
    numbers = [
        number
        for number in target.allowed_bays[agent_id]
        if (number in target.allowed_bays[other]) == shared
    ]
    return next(bay.cell for bay in target.bays[agent_id] if bay.number == numbers[0])


def second_target(scenario: MoveABoxScenario, crates: dict[str, Cell]) -> TargetLayout:
    """Round 1's second target, drawn the way the scenario draws it around ``crates``."""
    knobs = scenario.get_knobs()
    return draw_next_target(
        seed=knobs.seed,
        round_number=1,
        target_number=2,
        agent_ids=OPERATORS,
        crates=crates,
        pallets=first_depot(scenario=scenario).pallets,
        grid_size=knobs.grid_size,
        bay_count=knobs.bay_count,
        bays_allowed_each=knobs.bays_allowed_each,
        bays_differ=knobs.bays_differ,
        bay_identity=knobs.bay_identity,
    )


def two_target_scripts(
    first: dict[str, Cell], second: dict[str, Cell]
) -> dict[str, list[ScriptedTurn]]:
    """Each operator carries its crate to ``first``, then on to ``second``."""
    return {
        agent_id: [
            read(),
            *haul_path(directions=route_between(start=CORNER, end=first[agent_id]), method="cart"),
            finish(),
            wait_for_next_round(),
            *haul_path(
                directions=route_between(start=first[agent_id], end=second[agent_id]),
                method="cart",
            ),
            finish(),
            wait_for_next_round(),
        ]
        for agent_id in OPERATORS
    }
