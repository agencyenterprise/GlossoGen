"""The round loop through the real runner, tools and game clock, with scripted operators."""

import re
from pathlib import Path

import pytest

from glossogen.models.event import ToolResultReceived
from glossogen.scenarios.move_a_box.events import (
    MoveABoxActionTaken,
    MoveABoxNoteWritten,
    MoveABoxRoundResolved,
    MoveABoxRoundStarted,
)
from glossogen.scenarios.move_a_box.ids import (
    ALL_FINISHED_TRIGGER,
    BASE_TEMPERATURE,
    DELIVERY_POINTS,
    MATCH_BONUS,
    OPERATOR_A,
    OPERATOR_B,
    TEMPERATURE_DELTA,
)
from glossogen.testing.scenario_runtime import assert_round_loop_completed
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.simulation_harness import SimulationResult
from tests.scenarios.move_a_box.move_a_box_play import (
    ONE_ROUND,
    SHARED_BAY,
    TO_BAY_FOUR,
    TO_BAY_ONE,
    TO_BAY_THREE,
    TO_SHARED_BAY,
    build,
    finish,
    haul,
    haul_path,
    notepad,
    pack_ice,
    play,
    read,
    stand_by,
    to_shared_bay,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("move_a_box")


def resolved(result: SimulationResult) -> MoveABoxRoundResolved:
    [outcome] = result.of_type(event_type=MoveABoxRoundResolved)
    return outcome


def results_for(result: SimulationResult, agent_id: str, tool_name: str) -> list[str]:
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == tool_name
    ]


def temperatures_of(result: SimulationResult, agent_id: str) -> list[int]:
    return [
        event.temperature
        for event in result.of_type(event_type=MoveABoxActionTaken)
        if event.agent_id == agent_id
    ]


async def test_both_crates_on_one_bay_score_the_bonus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent_id: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()]
        for agent_id in (OPERATOR_A, OPERATOR_B)
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert_round_loop_completed(result=result, round_count=1)
    outcome = resolved(result=result)
    assert outcome.matched
    assert outcome.success
    assert outcome.trigger == ALL_FINISHED_TRIGGER
    assert outcome.final_bays == {OPERATOR_A: SHARED_BAY, OPERATOR_B: SHARED_BAY}
    assert outcome.points == {
        OPERATOR_A: DELIVERY_POINTS + MATCH_BONUS,
        OPERATOR_B: DELIVERY_POINTS + MATCH_BONUS,
    }


async def test_different_bays_score_delivery_without_the_bonus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            *haul_path(directions=TO_BAY_FOUR, method="cart"),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            *haul_path(directions=TO_BAY_THREE, method="cart"),
            finish(),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert outcome.final_bays == {OPERATOR_A: 4, OPERATOR_B: 3}
    assert not outcome.matched
    assert not outcome.success
    assert outcome.points == {OPERATOR_A: DELIVERY_POINTS, OPERATOR_B: DELIVERY_POINTS}


async def test_a_crate_left_off_a_bay_scores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
        OPERATOR_B: [
            read(),
            haul(method="cart", direction="right"),
            finish(),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert outcome.final_bays == {OPERATOR_A: SHARED_BAY, OPERATOR_B: None}
    assert outcome.points == {OPERATOR_A: DELIVERY_POINTS, OPERATOR_B: 0}


async def test_a_bay_the_depot_did_not_assign_scores_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bay 1 is open floor for operator_a, but the depot assigned it to operator_b."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            *haul_path(directions=TO_BAY_ONE, method="cart"),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            *haul_path(directions=TO_BAY_ONE, method="cart"),
            finish(),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert outcome.final_bays == {OPERATOR_A: None, OPERATOR_B: 1}
    assert outcome.points == {OPERATOR_A: 0, OPERATOR_B: DELIVERY_POINTS}
    assert not outcome.matched


async def test_each_action_moves_the_reading_by_its_own_amount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            haul(method="drag", direction="right"),
            haul(method="sled", direction="right"),
            haul(method="cart", direction="down"),
            stand_by(),
            pack_ice(),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    expected: list[int] = []
    reading = BASE_TEMPERATURE
    for action in ("drag", "sled", "cart", "stand_by", "pack_ice"):
        reading += TEMPERATURE_DELTA[action]
        expected.append(reading)
    assert temperatures_of(result=result, agent_id=OPERATOR_A) == expected


async def test_the_readout_shows_the_other_crate_only_as_a_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other crate's line carries its reading and status, never where it stands."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
        OPERATOR_B: [
            read(),
            *haul_path(directions=TO_BAY_THREE, method="drag"),
            finish(),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    readouts = results_for(result=result, agent_id=OPERATOR_A, tool_name="haul")
    assert readouts
    [started] = result.of_type(event_type=MoveABoxRoundStarted)
    partner_crate = started.crate_ids[OPERATOR_B]
    for readout in readouts:
        [partner_line] = [line for line in readout.splitlines() if partner_crate in line]
        assert "row" not in partner_line
        assert "col" not in partner_line
        assert "bay" not in partner_line
        # The reading itself is there: a temperature in degrees, not the crate id's C.
        assert re.search(r"\b\d+C\b", partner_line)


async def test_lockstep_shows_each_operator_the_other_crate_moving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A held action returns only once the other crate's reading has moved on."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
        OPERATOR_B: [read(), *to_shared_bay(method="drag"), finish(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    readouts = results_for(result=result, agent_id=OPERATOR_A, tool_name="haul")
    assert len(readouts) == len(TO_SHARED_BAY)
    # operator_b drags, so its reading climbs by 3 a step from 20. By the time
    # operator_a's last haul returns, every one of those steps has landed.
    assert "41C" in readouts[-1]


async def test_a_haul_off_the_floor_is_refused_and_spends_no_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The crate starts in the corner, so up and left leave the floor."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            haul(method="cart", direction="up"),
            haul(method="cart", direction="down"),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert outcome.final_bays[OPERATOR_A] is None
    assert outcome.steps_used[OPERATOR_A] == 1


async def test_the_notepad_is_private_and_costs_no_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            notepad(text="cart means bay one"),
            *to_shared_bay(method="cart"),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [note] = result.of_type(event_type=MoveABoxNoteWritten)
    assert note.agent_id == OPERATOR_A
    assert note.text == "cart means bay one"
    outcome = resolved(result=result)
    assert outcome.steps_used[OPERATOR_A] == len(TO_SHARED_BAY)
    for readout in results_for(result=result, agent_id=OPERATOR_B, tool_name="haul"):
        assert "cart means bay one" not in readout


async def test_a_crate_that_stopped_off_the_bays_is_not_called_delivered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Status is the only field besides the reading that crosses, so it must be true."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
        OPERATOR_B: [
            read(),
            haul(method="cart", direction="right"),
            finish(),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert outcome.final_bays[OPERATOR_B] is None
    [started] = result.of_type(event_type=MoveABoxRoundStarted)
    partner_crate = started.crate_ids[OPERATOR_B]
    seen = [
        line
        for readout in results_for(result=result, agent_id=OPERATOR_A, tool_name="haul")
        for line in readout.splitlines()
        if partner_crate in line
    ]
    assert seen
    for line in seen:
        assert "delivered" not in line


async def test_without_partner_readout_only_one_crate_is_on_the_readout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control rests on this: with it off, nothing of the other crate crosses."""
    scenario = build(preset_name="knobs_no_readout_control", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent_id: [read(), haul(method="cart", direction="right"), finish(), wait_for_next_round()]
        for agent_id in (OPERATOR_A, OPERATOR_B)
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [started] = result.of_type(event_type=MoveABoxRoundStarted)
    partner_crate = started.crate_ids[OPERATOR_B]
    readouts = results_for(result=result, agent_id=OPERATOR_A, tool_name="haul")
    assert readouts
    for readout in readouts:
        assert started.crate_ids[OPERATOR_A] in readout
        assert partner_crate not in readout
