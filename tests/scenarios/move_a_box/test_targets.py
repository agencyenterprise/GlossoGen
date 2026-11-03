"""Rounds of several targets, played through the real runner with scripted operators.

Each target is scored on its own once every crate has been left, the next target
is drawn around where the crates stand, and its briefing reaches every operator
in the same round. The round matches only when every target did.
"""

from pathlib import Path

import pytest

from glossogen.models.event import ToolResultReceived
from glossogen.scenarios.move_a_box.depot import Cell
from glossogen.scenarios.move_a_box.events import (
    MoveABoxRoundResolved,
    MoveABoxTargetResolved,
    MoveABoxTargetStarted,
)
from glossogen.scenarios.move_a_box.ids import (
    ALL_FINISHED_TRIGGER,
    DELIVERY_POINTS,
    MATCH_BONUS,
    OPERATOR_A,
    OPERATOR_B,
)
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.simulation_harness import SimulationResult
from tests.scenarios.move_a_box.move_a_box_play import (
    CORNER,
    ONE_ROUND,
    OPERATORS,
    TWO_TARGETS,
    bay_cell,
    build,
    finish,
    first_depot,
    haul,
    haul_path,
    play,
    read,
    route_between,
    second_target,
    two_target_scripts,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("move_a_box")


def reads_of(result: SimulationResult, agent_id: str) -> list[str]:
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == "read_notifications"
    ]


async def test_two_matched_targets_score_twice_and_match_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=TWO_TARGETS)
    first = {
        agent_id: bay_cell(
            target=first_depot(scenario=scenario).first_target, agent_id=agent_id, shared=True
        )
        for agent_id in OPERATORS
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

    targets = result.of_type(event_type=MoveABoxTargetResolved)
    assert [(event.target_number, event.matched) for event in targets] == [(1, True), (2, True)]
    [started] = result.of_type(event_type=MoveABoxTargetStarted)
    assert started.target_number == 2
    assert {
        crate_id.split("#")[0]: Cell(*cell) for crate_id, cell in targets[0].final_cells.items()
    } == first
    [resolved] = result.of_type(event_type=MoveABoxRoundResolved)
    assert resolved.matched
    assert resolved.trigger == ALL_FINISHED_TRIGGER
    both_targets = 2 * (DELIVERY_POINTS + MATCH_BONUS)
    assert resolved.points == {OPERATOR_A: both_targets, OPERATOR_B: both_targets}
    briefing = next(
        text for text in reads_of(result=result, agent_id=OPERATOR_A) if "TARGET 2" in text
    )
    assert "ROUND 1, TARGET 2 OF 2" in briefing
    assert "Round 1, target 1 result: you left a crate on the bay at" in briefing
    assert f"The crate is where you left it, at {first[OPERATOR_A].label()}." in briefing


async def test_a_missed_target_still_hands_out_the_next_and_the_round_does_not_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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

    targets = result.of_type(event_type=MoveABoxTargetResolved)
    assert [(event.target_number, event.matched) for event in targets] == [(1, False), (2, True)]
    [resolved] = result.of_type(event_type=MoveABoxRoundResolved)
    assert not resolved.matched
    one_miss_one_match = DELIVERY_POINTS + DELIVERY_POINTS + MATCH_BONUS
    assert resolved.points == {OPERATOR_A: one_miss_one_match, OPERATOR_B: one_miss_one_match}


async def test_acting_on_a_new_target_before_reading_its_briefing_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_b leaves its crate at once, so operator_a's finish opens target 2."""
    scenario = build(preset_name="knobs_default", overrides=TWO_TARGETS)
    first = bay_cell(
        target=first_depot(scenario=scenario).first_target, agent_id=OPERATOR_A, shared=True
    )
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            *haul_path(directions=route_between(start=CORNER, end=first), method="cart"),
            finish(),
            haul(method="cart", direction="up"),
            read(),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [read(), finish(), wait_for_next_round(), finish(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    hauls = [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == OPERATOR_A and event.tool_name == "haul"
    ]
    assert "Target 2 of round 1 has started and you have not read its briefing" in hauls[-1]
    assert any("TARGET 2 OF 2" in text for text in reads_of(result=result, agent_id=OPERATOR_A))
    assert len(result.of_type(event_type=MoveABoxTargetResolved)) == 2


def hauls_of(result: SimulationResult, agent_id: str) -> list[str]:
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == "haul"
    ]


async def test_every_readout_of_a_multi_target_round_restates_the_target_s_bays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An operator whose history lost a briefing finds its bays again on its next action."""
    scenario = build(preset_name="knobs_default", overrides=TWO_TARGETS)
    opening = first_depot(scenario=scenario).first_target
    first = {
        agent_id: bay_cell(target=opening, agent_id=agent_id, shared=True) for agent_id in OPERATORS
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

    hauls = hauls_of(result=result, agent_id=OPERATOR_A)
    listings = [
        line for text in hauls for line in text.splitlines() if line.startswith("Your bays")
    ]
    assert len(listings) == len(hauls)
    second_listing = "  ".join(
        bay.cell.label()
        for bay in target.bays[OPERATOR_A]
        if bay.number in target.allowed_bays[OPERATOR_A]
    )
    assert listings[-1] == f"Your bays for this target: {second_listing}."


async def test_a_one_target_readout_lists_no_bays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    cell = bay_cell(
        target=first_depot(scenario=scenario).first_target, agent_id=OPERATOR_A, shared=True
    )
    scripts: dict[str, list[ScriptedTurn]] = {
        agent_id: [
            read(),
            *haul_path(directions=route_between(start=CORNER, end=cell), method="cart"),
            finish(),
            wait_for_next_round(),
        ]
        for agent_id in (OPERATOR_A,)
    }
    scripts[OPERATOR_B] = [read(), finish(), wait_for_next_round()]
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert not any("Your bays" in text for text in hauls_of(result=result, agent_id=OPERATOR_A))
