"""What the run-detail panel is handed for a move_a_box run."""

from pathlib import Path

import pytest

from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B
from glossogen.scenarios.move_a_box.run_detail_extension import (
    MoveABoxRunDetailExtension,
    MoveABoxRunExtras,
)
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.simulation_harness import SimulationResult
from tests.scenarios.move_a_box.move_a_box_play import (
    ONE_ROUND,
    SHARED_BAY,
    build,
    finish,
    haul,
    pack_ice,
    play,
    read,
    stand_by,
    to_shared_bay,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("move_a_box")


def extras_of(result: SimulationResult) -> MoveABoxRunExtras:
    return MoveABoxRunDetailExtension().build_extras(
        events=result.events, agents_by_id={}, messages=[]
    )


async def played(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimulationResult:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            haul(method="drag", direction="right"),
            stand_by(),
            pack_ice(),
            haul(method="sled", direction="right"),
            haul(method="cart", direction="down"),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
    }
    return await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )


async def test_the_panel_gets_one_floor_per_operator_with_its_own_assigned_bays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extras = extras_of(result=await played(tmp_path=tmp_path, monkeypatch=monkeypatch))

    [round_floor] = extras.cases
    assert round_floor.grid_size == 7
    assert len(round_floor.bays) == 6
    assert round_floor.shared_bays == [SHARED_BAY]
    assert [floor.agent_id for floor in round_floor.operators] == [OPERATOR_A, OPERATOR_B]
    first, second = round_floor.operators
    assert first.allowed_bays != second.allowed_bays
    assert set(first.allowed_bays) & set(second.allowed_bays) == {SHARED_BAY}
    assert first.pallets == [] and second.pallets == []


async def test_every_action_reaches_the_panel_with_the_reading_it_took(  # noqa: D103
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extras = extras_of(result=await played(tmp_path=tmp_path, monkeypatch=monkeypatch))

    [round_floor] = extras.cases
    [floor] = [f for f in round_floor.operators if f.agent_id == OPERATOR_A]
    assert [step.action for step in floor.crates[0].steps] == [
        "drag",
        "stand_by",
        "pack_ice",
        "sled",
        "cart",
    ]
    assert [step.temperature for step in floor.crates[0].steps] == [23, 22, 20, 22, 23]
    assert [step.direction for step in floor.crates[0].steps] == [
        "right",
        None,
        None,
        "right",
        "down",
    ]
    assert floor.crates[0].final_bay is None
    assert floor.crates[0].finished


async def test_an_in_place_action_leaves_the_crate_where_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The floor plan draws a path, so a step that does not move must not add a point."""
    extras = extras_of(result=await played(tmp_path=tmp_path, monkeypatch=monkeypatch))

    [round_floor] = extras.cases
    [floor] = [f for f in round_floor.operators if f.agent_id == OPERATOR_A]
    stayed = [step for step in floor.crates[0].steps if step.direction is None]
    assert len(stayed) == 2
    for step in stayed:
        assert (step.cell.row, step.cell.col) == (1, 2)
