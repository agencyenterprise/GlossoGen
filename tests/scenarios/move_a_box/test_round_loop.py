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
    CRATE_A,
    CRATE_B,
    ONE_ROUND,
    SHARED_BAY,
    TO_BAY_FOUR,
    TO_BAY_ONE,
    TO_BAY_THREE,
    TO_SHARED_BAY,
    act,
    build,
    finish,
    haul,
    haul_burst,
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
    assert outcome.final_bays == {CRATE_A: SHARED_BAY, CRATE_B: SHARED_BAY}
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
    assert outcome.final_bays == {CRATE_A: 4, CRATE_B: 3}
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
    assert outcome.final_bays == {CRATE_A: SHARED_BAY, CRATE_B: None}
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
    assert outcome.final_bays == {CRATE_A: None, CRATE_B: 1}
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

    readouts = results_for(result=result, agent_id=OPERATOR_A, tool_name="act")
    assert readouts
    [started] = result.of_type(event_type=MoveABoxRoundStarted)
    partner_crate = started.crate_ids[CRATE_B]
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

    readouts = results_for(result=result, agent_id=OPERATOR_A, tool_name="act")
    # One act call per haul, and one more for the finish.
    assert len(readouts) == len(TO_SHARED_BAY) + 1
    # operator_b drags, so its reading climbs by 3 a step from 20. By the time
    # operator_a's last haul returns, every one of those steps has landed.
    assert "41C" in readouts[-2]


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
    assert outcome.final_bays[CRATE_A] is None
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
    for readout in results_for(result=result, agent_id=OPERATOR_B, tool_name="act"):
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
    assert outcome.final_bays[CRATE_B] is None
    [started] = result.of_type(event_type=MoveABoxRoundStarted)
    partner_crate = started.crate_ids[CRATE_B]
    seen = [
        line
        for readout in results_for(result=result, agent_id=OPERATOR_A, tool_name="act")
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
    partner_crate = started.crate_ids[CRATE_B]
    readouts = results_for(result=result, agent_id=OPERATOR_A, tool_name="act")
    assert readouts
    for readout in readouts:
        assert started.crate_ids[CRATE_A] in readout
        assert partner_crate not in readout


async def test_one_act_call_takes_every_action_in_the_list_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole route in one call: the point of the tool is a burst nothing interrupts."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            haul_burst(directions=TO_SHARED_BAY, method="cart"),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    taken = [
        event
        for event in result.of_type(event_type=MoveABoxActionTaken)
        if event.agent_id == OPERATOR_A
    ]
    assert [event.direction for event in taken] == TO_SHARED_BAY
    outcome = resolved(result=result)
    assert outcome.final_bays[CRATE_A] == SHARED_BAY
    assert outcome.steps_used[OPERATOR_A] == len(TO_SHARED_BAY)


async def test_a_burst_the_floor_refuses_stops_there_and_keeps_what_stood(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The crate starts in the corner, so a list that walks up leaves the floor part way."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            haul_burst(directions=["right", "right", "up", "down"], method="cart"),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    taken = [
        event
        for event in result.of_type(event_type=MoveABoxActionTaken)
        if event.agent_id == OPERATOR_A
    ]
    # The two rights stand; up leaves the floor and stops the list before down.
    assert [event.direction for event in taken] == ["right", "right"]
    outcome = resolved(result=result)
    assert outcome.steps_used[OPERATOR_A] == 2
    burst = results_for(result=result, agent_id=OPERATOR_A, tool_name="act")[0]
    assert "Stopped after 2 of 4 actions" in burst
    assert "leaves the floor" in burst


async def test_a_list_longer_than_the_knob_allows_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan the scenario will not take is refused whole, not applied as far as it fits."""
    overrides = {**ONE_ROUND, "actions_per_call": 3}
    scenario = build(preset_name="knobs_default", overrides=overrides)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            haul_burst(directions=["right", "right", "down", "down"], method="cart"),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    taken = [
        event
        for event in result.of_type(event_type=MoveABoxActionTaken)
        if event.agent_id == OPERATOR_A
    ]
    assert taken == []
    assert resolved(result=result).steps_used[OPERATOR_A] == 0


@pytest.mark.parametrize(
    ("steps", "refused"),
    [
        ([("cart", None)], "needs a direction"),
        ([("stand_by", "left")], "takes no direction"),
    ],
)
async def test_a_step_the_scenario_cannot_read_changes_nothing(
    steps: list[tuple[str, str | None]],
    refused: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A carrying action needs a direction and an action in place takes none."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act(steps=[*steps, ("cart", "right")]),
            finish(),
            wait_for_next_round(),
        ],
        OPERATOR_B: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    taken = [
        event
        for event in result.of_type(event_type=MoveABoxActionTaken)
        if event.agent_id == OPERATOR_A
    ]
    assert taken == []
    assert resolved(result=result).steps_used[OPERATOR_A] == 0
    refusals = results_for(result=result, agent_id=OPERATOR_A, tool_name="act")
    assert any(refused in text for text in refusals)


async def test_one_call_can_haul_and_finish_the_crate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finishing is a step of the list, so a round can be played in a single call."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    route: list[tuple[str, str | None]] = [("cart", direction) for direction in TO_SHARED_BAY]
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [read(), act(steps=[*route, ("finish", None)]), wait_for_next_round()],
        OPERATOR_B: [read(), act(steps=[*route, ("finish", None)]), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert outcome.final_bays[CRATE_A] == SHARED_BAY
    assert outcome.final_bays[CRATE_B] == SHARED_BAY
    assert outcome.matched
