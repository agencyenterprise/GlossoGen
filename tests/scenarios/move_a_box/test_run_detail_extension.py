"""What the run-detail panel is handed for a move_a_box run."""

from pathlib import Path
from typing import Any

import pytest

from glossogen.event_parsing import parse_event
from glossogen.scenarios.move_a_box.events import MoveABoxRoundStarted
from glossogen.scenarios.move_a_box.ids import BAY_LETTERS, BAY_SYMBOLS, OPERATOR_A, OPERATOR_B
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.simulation_harness import SimulationResult
from tests.scenarios.move_a_box.move_a_box_play import (
    ONE_ROUND,
    OPERATORS,
    SHARED_BAY,
    TWO_TARGETS,
    bay_cell,
    build,
    extras_of,
    finish,
    first_depot,
    haul,
    pack_ice,
    play,
    read,
    second_target,
    stand_by,
    to_shared_bay,
    two_target_scripts,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("move_a_box")


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
    assert round_floor.targets[0].shared_bays == [SHARED_BAY]
    for floor in round_floor.targets[0].operators:
        assert [bay.label for bay in floor.bays] == ["1", "2", "3", "4", "5", "6"]
        assert [bay.name for bay in floor.bays][SHARED_BAY - 1] == "6,3"
    assert [floor.agent_id for floor in round_floor.targets[0].operators] == [
        OPERATOR_A,
        OPERATOR_B,
    ]
    first, second = round_floor.targets[0].operators
    assert first.allowed_bays != second.allowed_bays
    assert set(first.allowed_bays) & set(second.allowed_bays) == {SHARED_BAY}
    assert first.pallets == [] and second.pallets == []


async def test_every_action_reaches_the_panel_with_the_reading_it_took(  # noqa: D103
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extras = extras_of(result=await played(tmp_path=tmp_path, monkeypatch=monkeypatch))

    [round_floor] = extras.cases
    [floor] = [f for f in round_floor.targets[0].operators if f.agent_id == OPERATOR_A]
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
    [floor] = [f for f in round_floor.targets[0].operators if f.agent_id == OPERATOR_A]
    stayed = [step for step in floor.crates[0].steps if step.direction is None]
    assert len(stayed) == 2
    for step in stayed:
        assert (step.cell.row, step.cell.col) == (1, 2)


@pytest.mark.parametrize(
    ("preset_name", "marks", "names"),
    [
        (
            "knobs_symbol_bays",
            tuple(symbol.glyph for symbol in BAY_SYMBOLS),
            tuple(symbol.name for symbol in BAY_SYMBOLS),
        ),
        ("knobs_letter_bays", BAY_LETTERS, BAY_LETTERS),
    ],
)
async def test_marked_floors_reach_the_panel_with_their_own_squares_and_marks(
    preset_name: str,
    marks: tuple[str, ...],
    names: tuple[str, ...],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = build(preset_name=preset_name, overrides=ONE_ROUND)
    depot = first_depot(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent_id: [read(), finish(), wait_for_next_round()] for agent_id in (OPERATOR_A, OPERATOR_B)
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    [round_floor] = extras_of(result=result).cases

    [shared] = round_floor.targets[0].shared_bays
    first, second = round_floor.targets[0].operators
    for floor in (first, second):
        assert sorted(bay.number for bay in floor.bays) == list(
            depot.first_target.allowed_bays[floor.agent_id]
        )
        for bay in floor.bays:
            assert bay.label == marks[bay.number - 1]
            assert bay.name == names[bay.number - 1]
    assert not {(bay.cell.row, bay.cell.col) for bay in first.bays} & {
        (bay.cell.row, bay.cell.col) for bay in second.bays
    }
    assert {bay.label for bay in first.bays if bay.number == shared} == {
        bay.label for bay in second.bays if bay.number == shared
    }


def test_a_round_recorded_with_one_shared_bay_list_reads_back_as_square_bays() -> None:
    """Runs logged before ``bay_identity`` carry one ``bays`` list every floor stood on."""
    record: dict[str, Any] = {
        "event_type": "move_a_box_round_started",
        "round_number": 1,
        "grid_size": 7,
        "start_cells": {OPERATOR_A: [1, 1], OPERATOR_B: [2, 2]},
        "bays": [[3, 5], [6, 3]],
        "pallets": {OPERATOR_A: [], OPERATOR_B: []},
        "allowed_bays": {OPERATOR_A: [1, 2], OPERATOR_B: [2]},
        "steps_per_round": 40,
        "crates_each": 1,
        "bays_differ": True,
        "crate_start": "separate_random",
        "partner_readout": True,
        "partner_disclosed": True,
        "partner_bay_disclosed": True,
        "crate_ids": {f"{OPERATOR_A}#1": "CR-1111", f"{OPERATOR_B}#1": "CR-2222"},
        "crate_masses": {f"{OPERATOR_A}#1": 30, f"{OPERATOR_B}#1": 40},
    }
    event = parse_event(raw=record)

    assert isinstance(event, MoveABoxRoundStarted)
    assert event.bay_identity == "square"
    for agent_id in (OPERATOR_A, OPERATOR_B):
        assert [
            (bay.number, bay.name, bay.mark, bay.cell) for bay in event.floor_bays[agent_id]
        ] == [
            (1, "3,5", "B", (3, 5)),
            (2, "6,3", "B", (6, 3)),
        ]


async def test_a_round_of_two_targets_reaches_the_panel_as_two_floors_each(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Target 2 starts each crate where target 1 left it, with target 2's own bays and steps."""
    scenario = build(preset_name="knobs_default", overrides=TWO_TARGETS)
    opening = first_depot(scenario=scenario).first_target
    first = {
        OPERATOR_A: bay_cell(target=opening, agent_id=OPERATOR_A, shared=False),
        OPERATOR_B: bay_cell(target=opening, agent_id=OPERATOR_B, shared=True),
    }
    target = second_target(scenario=scenario, crates=first)
    second = {
        agent_id: bay_cell(target=target, agent_id=agent_id, shared=True) for agent_id in OPERATORS
    }
    result = await play(
        scenario=scenario,
        scripts=two_target_scripts(first=first, second=second),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    extras = extras_of(result=result)

    assert extras.targets_per_round == 2
    [round_floor] = extras.cases
    assert not round_floor.matched
    one, two = round_floor.targets
    assert (one.target_number, one.scored, one.matched) == (1, True, False)
    assert (two.target_number, two.scored, two.matched) == (2, True, True)
    for floor_one, floor_two in zip(one.operators, two.operators, strict=True):
        [crate_one] = floor_one.crates
        [crate_two] = floor_two.crates
        assert floor_two.start == crate_one.final_cell
        assert (crate_one.final_cell.row, crate_one.final_cell.col) == tuple(
            first[floor_one.agent_id]
        )
        assert (crate_two.final_cell.row, crate_two.final_cell.col) == tuple(
            second[floor_two.agent_id]
        )
        assert crate_two.steps[0].sequence > crate_one.steps[-1].sequence
        assert [bay.number for bay in floor_two.bays] == [
            bay.number for bay in target.bays[floor_two.agent_id]
        ]
        assert floor_one.points == 10
        assert floor_two.points == 20
