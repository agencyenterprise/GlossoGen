"""``virtual_clock``: operators paced by simulated latency, and actions that take virtual time.

The scripted model answers every request at once, so the order these tests check
comes from the clock alone: a request costs a second plus its output tokens at 50 a
second, and under ``step_duration_s`` each action lands that long after the one
before it.
"""

from pathlib import Path
from typing import Any

import pytest

from glossogen.models.event import (
    AgentResumed,
    RoundAdvanced,
    SimulationEvent,
    ToolResultReceived,
    WaitRegistered,
)
from glossogen.runtime.scenario_tool import SCENARIO_TOOL_TIMEOUT_SECONDS
from glossogen.scenarios.move_a_box.depot import Cell, crate_tags
from glossogen.scenarios.move_a_box.events import (
    MoveABoxActionTaken,
    MoveABoxOperatorFinished,
    MoveABoxRequestReleased,
    MoveABoxRoundResolved,
    MoveABoxRoundStarted,
    MoveABoxTargetResolved,
)
from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B
from glossogen.scenarios.move_a_box.scenario import MoveABoxScenario
from glossogen.testing.scripted_agent import (
    EventGate,
    GatedTurn,
    ParallelToolTurn,
    ScriptedTurn,
    ToolTurn,
)
from glossogen.testing.simulation_harness import (
    SimulationResult,
    never_times_out,
    resume_simulation,
)
from tests.scenarios.move_a_box.move_a_box_play import (
    CORNER,
    ONE_ROUND,
    OPERATORS,
    TO_SHARED_BAY,
    TWO_TARGETS,
    act_with_reasoning,
    bay_cell,
    build,
    finish,
    first_depot,
    play,
    play_with_clock,
    read,
    route_between,
    second_target,
    step,
    steps_along,
    to_shared_bay,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("move_a_box")

CLOCK_ROUND: dict[str, Any] = {**ONE_ROUND, "batched_actions": True}
"""``ONE_ROUND`` on the clock preset, with the floor actions given as ``act`` lists."""

STEP_SECONDS = 5.0
"""The clock preset's ``step_duration_s``."""

FINISH = step(action="finish", direction=None)


def to_shared_bay_and_finish() -> list[dict[str, str | None]]:
    return [*steps_along(directions=TO_SHARED_BAY, method="cart"), FINISH]


def landings(result: SimulationResult, agent_id: str) -> list[MoveABoxActionTaken]:
    return [
        event
        for event in result.of_type(event_type=MoveABoxActionTaken)
        if event.agent_id == agent_id
    ]


def act_results(result: SimulationResult, agent_id: str) -> list[str]:
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == "act"
    ]


def test_the_clock_needs_lockstep_off_and_step_time_needs_the_clock() -> None:
    with pytest.raises(ValueError, match="virtual_clock needs lockstep off"):
        build(preset_name="knobs_virtual_clock", overrides={"lockstep": True})
    with pytest.raises(ValueError, match="step_duration_s applies only with virtual_clock"):
        build(preset_name="knobs_default", overrides={"step_duration_s": 5.0})


def test_a_call_whose_actions_take_time_may_run_for_the_whole_round() -> None:
    timed = build(preset_name="knobs_virtual_clock", overrides={})
    instant = build(preset_name="knobs_virtual_clock", overrides={"step_duration_s": 0.0})
    assert timed.scenario_tool_timeout_s() == timed.get_knobs().max_round_duration_seconds
    assert instant.scenario_tool_timeout_s() == SCENARIO_TOOL_TIMEOUT_SECONDS


async def test_actions_land_in_simulated_latency_order_not_arrival_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_a's long reasoning costs its request more virtual time than operator_b's."""
    scenario = build(
        preset_name="knobs_virtual_clock", overrides={**CLOCK_ROUND, "step_duration_s": 0.0}
    )
    long_reasoning = " ".join(f"word{index}" for index in range(600))
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act_with_reasoning(steps=to_shared_bay_and_finish(), reasoning=long_reasoning),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            act_with_reasoning(steps=to_shared_bay_and_finish(), reasoning="Short."),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    actions = result.of_type(event_type=MoveABoxActionTaken)
    assert [action.agent_id for action in actions] == [OPERATOR_B] * 7 + [OPERATOR_A] * 7
    releases = {
        agent_id: [
            e for e in result.of_type(event_type=MoveABoxRequestReleased) if e.agent_id == agent_id
        ]
        for agent_id in (OPERATOR_A, OPERATOR_B)
    }
    long_release = releases[OPERATOR_A][1]
    assert long_release.completed_at_s - long_release.started_at_s > 12.0
    assert releases[OPERATOR_B][1].completed_at_s < long_release.completed_at_s
    # With no step time a list lands whole at the instant its response is released.
    assert {action.virtual_time_s for action in landings(result=result, agent_id=OPERATOR_A)} == {
        long_release.completed_at_s
    }
    [outcome] = result.of_type(event_type=MoveABoxRoundResolved)
    assert outcome.matched


async def test_the_other_operator_acts_between_the_actions_of_a_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_b waits on the readout, is woken by operator_a's first landing and acts.

    operator_a's list takes seven steps of five virtual seconds, and operator_b's
    stand_by lands while it runs.
    """
    scenario = build(preset_name="knobs_virtual_clock", overrides=CLOCK_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act_with_reasoning(
                steps=to_shared_bay_and_finish(), reasoning="Head for the shared bay."
            ),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            read(),
            act_with_reasoning(
                steps=[step(action="stand_by", direction=None)], reasoning="Answer."
            ),
            act_with_reasoning(steps=to_shared_bay_and_finish(), reasoning="Follow."),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    first_list = landings(result=result, agent_id=OPERATOR_A)
    times = [action.virtual_time_s for action in first_list if action.virtual_time_s is not None]
    assert len(times) == len(first_list) == 7
    assert [later - earlier for earlier, later in zip(times, times[1:])] == pytest.approx(
        [STEP_SECONDS] * 6
    )
    stand_by = next(
        action
        for action in landings(result=result, agent_id=OPERATOR_B)
        if action.action == "stand_by"
    )
    assert first_list[0].sequence < stand_by.sequence < first_list[-1].sequence
    assert stand_by.virtual_time_s is not None
    [a_finished] = [
        e for e in result.of_type(event_type=MoveABoxOperatorFinished) if e.agent_id == OPERATOR_A
    ]
    # A finish takes no time: it lands with the last haul.
    assert a_finished.virtual_time_s == times[-1]
    [outcome] = result.of_type(event_type=MoveABoxRoundResolved)
    assert outcome.matched


async def test_a_refused_action_stops_a_timed_list_before_its_time_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The crate starts in the corner, so the list's third action would leave the floor.

    The call returns when the second action lands, which is when operator_a's
    next request starts.
    """
    scenario = build(preset_name="knobs_virtual_clock", overrides=CLOCK_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act_with_reasoning(
                steps=steps_along(directions=["right", "right", "up", "down"], method="cart"),
                reasoning="Walk off the edge.",
            ),
            act_with_reasoning(steps=[FINISH], reasoning="Stay."),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            act_with_reasoning(steps=to_shared_bay_and_finish(), reasoning="Go."),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    taken = landings(result=result, agent_id=OPERATOR_A)
    times = [action.virtual_time_s for action in taken if action.virtual_time_s is not None]
    assert [action.direction for action in taken] == ["right", "right"]
    assert len(times) == 2 and times[1] - times[0] == pytest.approx(STEP_SECONDS)
    stopped = act_results(result=result, agent_id=OPERATOR_A)[0]
    assert "Stopped after 2 of 4 actions: Hauling up from 1,3 leaves the floor." in stopped
    next_starts = [
        e.started_at_s
        for e in result.of_type(event_type=MoveABoxRequestReleased)
        if e.agent_id == OPERATOR_A
    ]
    assert times[1] in next_starts


async def test_a_finish_refused_partway_through_a_timed_list_stops_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With two crates, finishing the first twice stops the list at the second finish."""
    scenario = build(preset_name="knobs_virtual_clock", overrides={**CLOCK_ROUND, "crates_each": 2})
    tags = crate_tags(seed=scenario.get_knobs().seed, crate_ids=scenario.get_world().crate_ids)
    a_first, a_second = (tags[f"{OPERATOR_A}#{slot}"].crate_id for slot in (1, 2))
    b_first, b_second = (tags[f"{OPERATOR_B}#{slot}"].crate_id for slot in (1, 2))

    def on(crate: str, action: str, direction: str | None) -> dict[str, str | None]:
        return {"crate": crate, "action": action, "direction": direction}

    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act_with_reasoning(
                steps=[
                    on(crate=a_first, action="finish", direction=None),
                    on(crate=a_first, action="finish", direction=None),
                    on(crate=a_second, action="cart", direction="right"),
                ],
                reasoning="Finish twice.",
            ),
            act_with_reasoning(
                steps=[on(crate=a_second, action="finish", direction=None)], reasoning="Done."
            ),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            act_with_reasoning(
                steps=[
                    on(crate=b_first, action="finish", direction=None),
                    on(crate=b_second, action="finish", direction=None),
                ],
                reasoning="Done.",
            ),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    stopped = act_results(result=result, agent_id=OPERATOR_A)[0]
    assert "Stopped after 1 of 3 actions: You already finished this crate this round." in stopped
    assert landings(result=result, agent_id=OPERATOR_A) == []
    finished = [
        e.crate_marking
        for e in result.of_type(event_type=MoveABoxOperatorFinished)
        if e.agent_id == OPERATOR_A
    ]
    assert finished == [a_first, a_second]


async def test_a_wait_with_a_timeout_counts_virtual_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_b's three-second wait ends before operator_a's first action has taken its five."""
    scenario = build(preset_name="knobs_virtual_clock", overrides=CLOCK_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act_with_reasoning(
                steps=to_shared_bay_and_finish(), reasoning="Head for the shared bay."
            ),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            ToolTurn(tool_name="read_notifications", args={"timeout_s": 3}),
            act_with_reasoning(steps=to_shared_bay_and_finish(), reasoning="Follow."),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [timed_wait] = [
        e
        for e in result.of_type(event_type=WaitRegistered)
        if e.agent_id == OPERATOR_B and e.deadline_s is not None
    ]
    resumed = next(
        e for e in result.of_type(event_type=AgentResumed) if e.wait_id == timed_wait.wait_id
    )
    assert resumed.wake_reasons == ["timeout"]
    assert resumed.waited_seconds == 3.0


async def test_a_round_that_ends_partway_through_a_list_says_how_much_landed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The phase ends once operator_a's first action has landed and its second is under way.

    operator_b is mid-request until the round resolves, so operator_a's second
    action cannot land before the round's end. The test waits on no duration.
    """
    scenario = build(preset_name="knobs_virtual_clock", overrides=CLOCK_ROUND)
    world = scenario.get_world()

    def ends_once_operator_a_has_landed_one(phase_age: float, limit: float) -> bool:
        _ = phase_age, limit
        return world.round_open and world.steps_used(agent_id=OPERATOR_A) >= 1

    def round_resolved(event: dict[str, object]) -> bool:
        return event["event_type"] == "move_a_box_round_resolved"

    scripts: dict[str, list[GatedTurn]] = {
        OPERATOR_A: [
            read(),
            act_with_reasoning(
                steps=steps_along(directions=["right", "right", "right"], method="cart"),
                reasoning="Head right.",
            ),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            read(),
            EventGate(matches=round_resolved, description="round 1 resolves"),
            wait_for_next_round(),
        ],
    }
    result = await play_with_clock(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=ends_once_operator_a_has_landed_one,
    )

    assert len(landings(result=result, agent_id=OPERATOR_A)) == 1
    assert act_results(result=result, agent_id=OPERATOR_A) == [
        "Round 1 ended after 1 of 3 actions landed. Call read_notifications(wait_for='next_round')."
    ]


async def test_two_timed_calls_in_one_response_land_one_after_the_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_a sends two act calls at once; the second waits for the first to land.

    Either order leaves the crate on 2,2, from where the third call takes it on.
    """
    scenario = build(preset_name="knobs_virtual_clock", overrides=CLOCK_ROUND)
    right = act_with_reasoning(
        steps=steps_along(directions=["right"], method="cart"), reasoning="R."
    )
    down = act_with_reasoning(steps=steps_along(directions=["down"], method="cart"), reasoning="D.")
    rest = [
        *steps_along(
            directions=route_between(start=Cell(row=2, col=2), end=Cell(row=6, col=3)),
            method="cart",
        ),
        FINISH,
    ]
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            ParallelToolTurn(calls=(right, down)),
            act_with_reasoning(steps=rest, reasoning="On to the shared bay."),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            act_with_reasoning(steps=to_shared_bay_and_finish(), reasoning="Go."),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    first, second = landings(result=result, agent_id=OPERATOR_A)[:2]
    assert first.virtual_time_s is not None and second.virtual_time_s is not None
    assert second.virtual_time_s - first.virtual_time_s == pytest.approx(STEP_SECONDS)
    assert all("Stopped" not in text for text in act_results(result=result, agent_id=OPERATOR_A))
    [outcome] = result.of_type(event_type=MoveABoxRoundResolved)
    assert outcome.matched


async def test_a_single_action_lands_its_step_time_after_its_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the four one-action tools, each haul lands five virtual seconds after its response."""
    scenario = build(preset_name="knobs_virtual_clock", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent_id: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()]
        for agent_id in OPERATORS
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    for agent_id in OPERATORS:
        released = {
            e.completed_at_s + STEP_SECONDS
            for e in result.of_type(event_type=MoveABoxRequestReleased)
            if e.agent_id == agent_id
        }
        hauls = landings(result=result, agent_id=agent_id)
        assert len(hauls) == len(TO_SHARED_BAY)
        assert all(haul.virtual_time_s in released for haul in hauls)
    [outcome] = result.of_type(event_type=MoveABoxRoundResolved)
    assert outcome.matched


async def test_a_timed_list_that_finishes_a_target_hands_out_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second operator's finish opens target 2 after its readout is rendered."""
    scenario = build(
        preset_name="knobs_virtual_clock", overrides={**TWO_TARGETS, "batched_actions": True}
    )
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

    def whole_target(start: Cell, end: Cell) -> ScriptedTurn:
        return act_with_reasoning(
            steps=[
                *steps_along(directions=route_between(start=start, end=end), method="cart"),
                FINISH,
            ],
            reasoning="To the bay.",
        )

    scripts: dict[str, list[ScriptedTurn]] = {
        agent_id: [
            read(),
            whole_target(start=CORNER, end=first[agent_id]),
            wait_for_next_round(),
            whole_target(start=first[agent_id], end=second[agent_id]),
            wait_for_next_round(),
        ]
        for agent_id in OPERATORS
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    targets = result.of_type(event_type=MoveABoxTargetResolved)
    assert [(event.target_number, event.matched) for event in targets] == [(1, True), (2, True)]
    for agent_id in OPERATORS:
        first_call = act_results(result=result, agent_id=agent_id)[0]
        assert "for target 1 of round 1" in first_call
        assert "Round 1, target 1, action" in first_call


def virtual_times(events: list[SimulationEvent]) -> list[float]:
    """Every virtual instant the events record."""
    times: list[float] = []
    for event in events:
        if isinstance(event, MoveABoxRequestReleased):
            times.extend((event.started_at_s, event.completed_at_s))
        elif (
            isinstance(event, (MoveABoxActionTaken, MoveABoxOperatorFinished, MoveABoxRoundStarted))
            and event.virtual_time_s is not None
        ):
            times.append(event.virtual_time_s)
    return times


async def test_a_resumed_run_carries_virtual_time_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Round 1 is played, the log is cut where round 2 begins, and the run resumes there."""
    scenario = build(preset_name="knobs_virtual_clock", overrides={**CLOCK_ROUND, "round_count": 2})
    round_one: dict[str, list[ScriptedTurn]] = {
        agent_id: [
            read(),
            act_with_reasoning(steps=to_shared_bay_and_finish(), reasoning="Go."),
            wait_for_next_round(),
        ]
        for agent_id in OPERATORS
    }
    played = await play(
        scenario=scenario, scripts=round_one, tmp_path=tmp_path / "source", monkeypatch=monkeypatch
    )
    cut = played.first_index(event_type=RoundAdvanced, round_number=2)
    lines = played.log_path.read_text(encoding="utf-8").splitlines(keepends=True)
    resumed_dir = tmp_path / "resumed"
    resumed_dir.mkdir()
    (resumed_dir / f"{MoveABoxScenario.name()}.jsonl").write_text(
        "".join(lines[:cut]), encoding="utf-8"
    )

    round_two: dict[str, list[ScriptedTurn]] = {
        agent_id: [
            read(),
            act_with_reasoning(
                steps=[step(action="stand_by", direction=None), FINISH], reasoning="Stay."
            ),
            wait_for_next_round(),
        ]
        for agent_id in OPERATORS
    }
    resumed = await resume_simulation(
        scenario=MoveABoxScenario.create_from_config(
            config=scenario.get_knobs().model_dump(mode="json")
        ),
        scripts=round_two,
        run_dir=resumed_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    before = virtual_times(events=resumed.events[:cut])
    after = virtual_times(events=resumed.events[cut:])
    assert max(before) > 0.0
    assert after
    assert min(after) >= max(before)
