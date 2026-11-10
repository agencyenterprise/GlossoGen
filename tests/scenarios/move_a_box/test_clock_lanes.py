"""The clock lanes the run-detail panel gets for a move_a_box run on the virtual clock.

The scripted model answers every request at once, so every time below comes from
the clock: a request costs a second plus its output tokens at 50 a second, and
each action takes the preset's five seconds.
"""

from pathlib import Path

import pytest

from glossogen.scenarios.move_a_box.clock_lanes import (
    MoveABoxClockLane,
    MoveABoxRoundClock,
    MoveABoxWakeCause,
)
from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B
from glossogen.scenarios.move_a_box.run_detail_extension import (
    MoveABoxRunExtras,
)
from glossogen.testing.scripted_agent import EventGate, GatedTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import never_times_out
from tests.scenarios.move_a_box.move_a_box_play import (
    FINISH,
    ONE_ROUND,
    STEP_SECONDS,
    TIMED_ROUND,
    TO_SHARED_BAY,
    act_with_reasoning,
    build,
    extras_of,
    finish,
    notepad,
    play,
    play_with_clock,
    read,
    step,
    steps_to_shared_bay_and_finish,
    to_shared_bay,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("move_a_box")


def clock_of(extras: MoveABoxRunExtras, round_number: int) -> MoveABoxRoundClock:
    [case] = [case for case in extras.cases if case.round_number == round_number]
    assert case.clock is not None
    return case.clock


def lane_of(clock: MoveABoxRoundClock, agent_id: str) -> MoveABoxClockLane:
    [lane] = [lane for lane in clock.lanes if lane.agent_id == agent_id]
    return lane


def assert_lane_is_unbroken(lane: MoveABoxClockLane) -> None:
    """Each span starts where the one before it ended, from the round's first second."""
    spans = sorted(
        [
            *((span.start_s, span.end_s) for span in lane.thinking),
            *((span.start_s, span.end_s) for span in lane.actions),
            *((span.start_s, span.end_s) for span in lane.waits),
        ]
    )
    assert spans[0][0] == pytest.approx(0.0)
    for (_, earlier_end), (later_start, _) in zip(spans, spans[1:], strict=False):
        assert later_start == pytest.approx(earlier_end)


async def test_a_run_with_the_clock_off_has_no_lanes(
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

    assert [case.clock for case in extras_of(result=result).cases] == [None]


async def test_a_wait_ends_where_the_other_operators_action_landed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_b waits on the readout and is woken by operator_a's first landing.

    Every second of the round is in one span or another, on both lanes.
    """
    scenario = build(preset_name="knobs_virtual_clock", overrides=TIMED_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act_with_reasoning(
                steps=steps_to_shared_bay_and_finish(), reasoning="Head for the shared bay."
            ),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            read(),
            act_with_reasoning(
                steps=[step(action="stand_by", direction=None)], reasoning="Answer."
            ),
            act_with_reasoning(steps=steps_to_shared_bay_and_finish(), reasoning="Follow."),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    clock = clock_of(extras=extras_of(result=result), round_number=1)
    lane_a = lane_of(clock=clock, agent_id=OPERATOR_A)
    lane_b = lane_of(clock=clock, agent_id=OPERATOR_B)
    assert [span.end_s - span.start_s for span in lane_a.actions] == pytest.approx(
        [STEP_SECONDS] * len(TO_SHARED_BAY)
    )
    [a_finish] = lane_a.finishes
    assert a_finish.at_s == pytest.approx(lane_a.actions[-1].end_s)
    [woken] = [wait for wait in lane_b.waits if wait.cause is MoveABoxWakeCause.OTHER_ACTED]
    assert woken.woken_by == OPERATOR_A
    assert woken.end_s == pytest.approx(lane_a.actions[0].end_s)
    assert woken.end_s > woken.start_s
    for span in lane_b.thinking:
        assert span.cost_s == pytest.approx(span.end_s - span.start_s)
        assert span.output_tokens > 0
    for lane in (lane_a, lane_b):
        assert_lane_is_unbroken(lane=lane)


async def test_a_timed_wait_ends_on_its_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_b's three-second wait ends before operator_a's first action has taken its five."""
    scenario = build(preset_name="knobs_virtual_clock", overrides=TIMED_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act_with_reasoning(steps=steps_to_shared_bay_and_finish(), reasoning="Go."),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            ToolTurn(tool_name="read_notifications", args={"timeout_s": 3}),
            act_with_reasoning(steps=steps_to_shared_bay_and_finish(), reasoning="Follow."),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    lane_b = lane_of(
        clock=clock_of(extras=extras_of(result=result), round_number=1), agent_id=OPERATOR_B
    )
    [timed] = [wait for wait in lane_b.waits if wait.timeout_s is not None]
    assert timed.timeout_s == 3.0
    assert timed.cause is MoveABoxWakeCause.TIMER
    assert timed.woken_by is None
    assert timed.end_s - timed.start_s == pytest.approx(3.0)


def round_two_started(event: dict[str, object]) -> bool:
    return event["event_type"] == "move_a_box_round_started" and event["round_number"] == 2


async def test_a_request_that_runs_into_the_next_round_shows_in_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_a writes a long note after finishing; operator_b finishes round 1 meanwhile.

    operator_b's model call is held until round 2 has started, so the clock
    stands at operator_b's finish when round 2 begins. operator_a's request ends
    round 1's lane and starts round 2's, and both keep its whole cost.
    """
    overrides = {**TIMED_ROUND, "round_count": 2, "notepad_enabled": True}
    scenario = build(preset_name="knobs_virtual_clock", overrides=overrides)
    long_note = " ".join(f"word{index}" for index in range(600))
    scripts: dict[str, list[GatedTurn]] = {
        OPERATOR_A: [
            read(),
            act_with_reasoning(steps=steps_to_shared_bay_and_finish(), reasoning="Go."),
            notepad(text=long_note),
            read(),
            act_with_reasoning(steps=[FINISH], reasoning="Stay."),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            act_with_reasoning(
                steps=[step(action="stand_by", direction=None), *steps_to_shared_bay_and_finish()],
                reasoning="Go.",
            ),
            EventGate(matches=round_two_started, description="round 2 starts"),
            read(),
            act_with_reasoning(steps=[FINISH], reasoning="Stay."),
            wait_for_next_round(),
        ],
    }
    result = await play_with_clock(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    extras = extras_of(result=result)
    round_one = clock_of(extras=extras, round_number=1)
    round_two = clock_of(extras=extras, round_number=2)
    note_in_one = lane_of(clock=round_one, agent_id=OPERATOR_A).thinking[-1]
    note_in_two = lane_of(clock=round_two, agent_id=OPERATOR_A).thinking[0]
    assert note_in_one.output_tokens == note_in_two.output_tokens
    assert note_in_one.cost_s == note_in_two.cost_s
    assert note_in_one.end_s == pytest.approx(round_one.duration_s)
    assert note_in_two.start_s == 0.0
    shown = (note_in_one.end_s - note_in_one.start_s) + (note_in_two.end_s - note_in_two.start_s)
    assert shown == pytest.approx(note_in_one.cost_s)
    assert note_in_one.end_s - note_in_one.start_s < note_in_one.cost_s
