"""``batched_actions``: one ``act`` call takes a list of actions, played through the real runner.

No other operator reads the readout until the list is done. What the scenario
cannot read is refused whole, and what the floor refuses stops the list where it
happens.
"""

import re
from pathlib import Path
from typing import Any

import pytest

from glossogen.models.event import ToolResultReceived
from glossogen.scenarios.move_a_box.depot import crate_tags
from glossogen.scenarios.move_a_box.events import (
    MoveABoxActionTaken,
    MoveABoxRoundResolved,
    MoveABoxRoundStarted,
    MoveABoxTargetResolved,
)
from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B
from glossogen.scenarios.move_a_box.planned_action import PlannedCrateStep
from glossogen.testing.scripted_agent import EventGate, GatedTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult
from tests.scenarios.move_a_box.move_a_box_play import (
    BATCHED_ROUND,
    CORNER,
    CRATE_A,
    FINISH,
    OPERATORS,
    SHARED_BAY,
    TO_SHARED_BAY,
    TWO_TARGETS,
    act,
    bay_cell,
    build,
    first_depot,
    play,
    play_with_clock,
    read,
    route_between,
    second_target,
    step,
    steps_along,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("move_a_box")


def resolved(result: SimulationResult) -> MoveABoxRoundResolved:
    [outcome] = result.of_type(event_type=MoveABoxRoundResolved)
    return outcome


def act_results(result: SimulationResult, agent_id: str) -> list[str]:
    return [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.agent_id == agent_id and event.tool_name == "act"
    ]


def actions_of(result: SimulationResult, agent_id: str) -> list[MoveABoxActionTaken]:
    return [
        event
        for event in result.of_type(event_type=MoveABoxActionTaken)
        if event.agent_id == agent_id
    ]


def to_shared_bay_and_finish() -> list[ScriptedTurn]:
    """One call to the shared bay by cart, one call to finish, and the wait."""
    return [
        read(),
        act(steps=steps_along(directions=TO_SHARED_BAY, method="cart")),
        act(steps=[FINISH]),
        wait_for_next_round(),
    ]


def test_batched_actions_offers_act_in_place_of_the_four_action_tools() -> None:
    batched = build(preset_name="knobs_default", overrides={})
    single = build(preset_name="knobs_default", overrides={"batched_actions": False})

    assert [tool.name for tool in batched.get_tools()] == ["act"]
    assert [tool.name for tool in single.get_tools()] == [
        "haul",
        "stand_by",
        "pack_ice",
        "finish",
    ]
    for agent in batched.get_agents(default_model="model", default_provider="openai"):
        assert agent.tool_names == ["act"]


def test_only_a_batched_run_tells_the_operators_about_act() -> None:
    batched = build(preset_name="knobs_default", overrides={})
    single = build(preset_name="knobs_default", overrides={"batched_actions": False})

    batched_prompts = batched.runner_prompts(agent_id=OPERATOR_A)
    single_prompts = single.runner_prompts(agent_id=OPERATOR_A)
    assert batched_prompts is not None
    assert single_prompts is not None
    assert "act(steps, reasoning)" in batched_prompts.system_suffix
    assert "haul(" not in batched_prompts.system_suffix
    assert "act(" not in single_prompts.system_suffix
    assert (
        "with act"
        in batched.get_agents(default_model="model", default_provider="openai")[0].system_prompt
    )


async def test_one_act_call_takes_every_action_in_the_list_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=BATCHED_ROUND)
    scripts = {agent_id: to_shared_bay_and_finish() for agent_id in OPERATORS}
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    taken = actions_of(result=result, agent_id=OPERATOR_A)
    assert [event.direction for event in taken] == TO_SHARED_BAY
    assert [event.steps_used for event in taken] == list(range(1, len(TO_SHARED_BAY) + 1))
    outcome = resolved(result=result)
    assert outcome.final_bays[CRATE_A] == SHARED_BAY
    assert outcome.steps_used[OPERATOR_A] == len(TO_SHARED_BAY)
    assert outcome.matched
    route_result = act_results(result=result, agent_id=OPERATOR_A)[0]
    assert f"{len(TO_SHARED_BAY)}. You hauled" in route_result


async def test_a_list_has_no_length_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Forty actions in place, then the route and the finish, all in one call."""
    waiting = [step(action="stand_by", direction=None)] * 40
    scenario = build(preset_name="knobs_default", overrides=BATCHED_ROUND)
    whole_round = [*waiting, *steps_along(directions=TO_SHARED_BAY, method="cart"), FINISH]
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [read(), act(steps=whole_round), wait_for_next_round()],
        OPERATOR_B: to_shared_bay_and_finish(),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert len(act_results(result=result, agent_id=OPERATOR_A)) == 1
    outcome = resolved(result=result)
    assert outcome.steps_used[OPERATOR_A] == len(waiting) + len(TO_SHARED_BAY)
    assert outcome.final_bays[CRATE_A] == SHARED_BAY


async def test_one_call_can_haul_and_finish_the_crate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finishing is a step of the list, so a round can be played in a single call."""
    scenario = build(preset_name="knobs_default", overrides=BATCHED_ROUND)
    whole_round = [*steps_along(directions=TO_SHARED_BAY, method="cart"), FINISH]
    scripts: dict[str, list[ScriptedTurn]] = {
        agent_id: [read(), act(steps=whole_round), wait_for_next_round()] for agent_id in OPERATORS
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    outcome = resolved(result=result)
    assert outcome.matched
    assert all(bay == SHARED_BAY for bay in outcome.final_bays.values())


async def test_a_list_the_floor_refuses_stops_there_and_keeps_what_stood(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The crate starts in the corner, so a list that walks up leaves the floor part way."""
    scenario = build(preset_name="knobs_default", overrides=BATCHED_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act(steps=steps_along(directions=["right", "right", "up", "down"], method="cart")),
            act(steps=[FINISH]),
            wait_for_next_round(),
        ],
        OPERATOR_B: to_shared_bay_and_finish(),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    taken = actions_of(result=result, agent_id=OPERATOR_A)
    assert [event.direction for event in taken] == ["right", "right"]
    assert resolved(result=result).steps_used[OPERATOR_A] == 2
    stopped = act_results(result=result, agent_id=OPERATOR_A)[0]
    assert "Stopped after 2 of 4 actions" in stopped
    assert "leaves the floor" in stopped


@pytest.mark.parametrize(
    ("steps", "refused"),
    [
        (
            [step(action="cart", direction=None), step(action="cart", direction="right")],
            "needs a direction",
        ),
        (
            [step(action="stand_by", direction="left"), step(action="cart", direction="right")],
            "takes no direction",
        ),
        ([], "at least one action"),
    ],
)
async def test_a_list_the_scenario_cannot_read_changes_nothing(
    steps: list[dict[str, str | None]],
    refused: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = build(preset_name="knobs_default", overrides=BATCHED_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [read(), act(steps=steps), act(steps=[FINISH]), wait_for_next_round()],
        OPERATOR_B: to_shared_bay_and_finish(),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert actions_of(result=result, agent_id=OPERATOR_A) == []
    assert resolved(result=result).steps_used[OPERATOR_A] == 0
    assert refused in act_results(result=result, agent_id=OPERATOR_A)[0]


async def test_the_other_operator_reads_only_the_finished_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_a drags the whole route in one call, so its reading jumps from 20 to 41.

    With ``readout_history`` off the readout carries the current reading alone,
    and operator_b, acting one step a call, never reads anything in between.
    """
    scenario = build(
        preset_name="knobs_default", overrides={**BATCHED_ROUND, "readout_history": False}
    )
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act(steps=steps_along(directions=TO_SHARED_BAY, method="drag")),
            act(steps=[FINISH]),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            *[act(steps=[step(action="cart", direction=direction)]) for direction in TO_SHARED_BAY],
            act(steps=[FINISH]),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [started] = result.of_type(event_type=MoveABoxRoundStarted)
    partner_crate = started.crate_ids[CRATE_A]
    seen = {
        int(match.group(1))
        for readout in act_results(result=result, agent_id=OPERATOR_B)
        for line in readout.splitlines()
        if partner_crate in line
        for match in [re.search(r"(-?\d+)C", line)]
        if match is not None
    }
    assert 41 in seen
    assert seen <= {20, 41}


async def test_a_list_that_finishes_a_target_hands_out_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(
        preset_name="knobs_default", overrides={**TWO_TARGETS, "batched_actions": True}
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

    def whole_target(start: Any, end: Any) -> ScriptedTurn:
        return act(
            steps=[
                *steps_along(directions=route_between(start=start, end=end), method="cart"),
                FINISH,
            ]
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
        # Rendered before the next target opens, whichever operator's list opened it.
        assert "Round 1, target 1, action" in first_call
        assert "left there for the target" in first_call


async def test_with_several_crates_each_step_names_its_crate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A step naming a crate the operator does not work refuses the whole list."""
    scenario = build(preset_name="knobs_default", overrides={**BATCHED_ROUND, "crates_each": 2})
    tags = crate_tags(seed=scenario.get_knobs().seed, crate_ids=scenario.get_world().crate_ids)
    a_first, a_second = (tags[f"{OPERATOR_A}#{slot}"].crate_id for slot in (1, 2))
    b_first, b_second = (tags[f"{OPERATOR_B}#{slot}"].crate_id for slot in (1, 2))

    def on(crate: str, action: str, direction: str | None) -> dict[str, str | None]:
        return {"crate": crate, "action": action, "direction": direction}

    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [
            read(),
            act(
                steps=[
                    on(crate=a_second, action="cart", direction="right"),
                    on(crate=b_first, action="finish", direction=None),
                ]
            ),
            act(
                steps=[
                    on(crate=a_second, action="cart", direction="right"),
                    on(crate=a_first, action="stand_by", direction=None),
                ]
            ),
            act(
                steps=[
                    on(crate=a_first, action="finish", direction=None),
                    on(crate=a_second, action="finish", direction=None),
                ]
            ),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
            read(),
            act(
                steps=[
                    on(crate=b_first, action="finish", direction=None),
                    on(crate=b_second, action="finish", direction=None),
                ]
            ),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    taken = actions_of(result=result, agent_id=OPERATOR_A)
    assert [(event.crate_marking, event.action) for event in taken] == [
        (a_second, "cart"),
        (a_first, "stand_by"),
    ]
    refusal = act_results(result=result, agent_id=OPERATOR_A)[0]
    assert f"Action 2 names {b_first!r}, which is not a crate you are working" in refusal
    assert refusal.endswith("Nothing happened.")


def test_without_partner_disclosed_nothing_says_other_operators_wait_on_the_list() -> None:
    """``knobs_no_readout_control`` tells an operator nothing about the others."""
    scenario = build(preset_name="knobs_no_readout_control", overrides={})
    [act_tool] = [tool for tool in scenario.get_tools() if tool.name == "act"]
    system_prompt = scenario.get_agents(default_model="model", default_provider="openai")[
        0
    ].system_prompt

    assert "other operator" not in system_prompt
    assert "other operator" not in act_tool.description
    disclosed = build(preset_name="knobs_default", overrides={})
    [disclosed_act] = [tool for tool in disclosed.get_tools() if tool.name == "act"]
    assert "No other operator reads the depot readout" in disclosed_act.description


def test_the_step_schema_carries_no_developer_docstring() -> None:
    """Only ``Direction``'s description reaches the model, the one ``haul`` sends too."""
    schema = PlannedCrateStep.model_json_schema()
    descriptions = [
        definition["description"]
        for definition in [schema, *schema["$defs"].values()]
        if "description" in definition
    ]

    assert descriptions == ["The neighbouring square an action moves the crate to."]


async def test_running_out_of_steps_mid_list_points_at_act(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={**BATCHED_ROUND, "steps_per_round": 7})
    waiting = [step(action="stand_by", direction=None)] * 9
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [read(), act(steps=waiting), wait_for_next_round()],
        OPERATOR_B: to_shared_bay_and_finish(),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    stopped = act_results(result=result, agent_id=OPERATOR_A)[0]
    assert "Stopped after 7 of 9 actions: You have no steps left this round." in stopped
    assert "Call act with finish for every crate still open." in stopped
    assert "Call finish" not in stopped


async def test_a_list_with_no_reasoning_is_refused_as_a_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=BATCHED_ROUND)
    unreasoned = ToolTurn(
        tool_name="act",
        args={"steps": [step(action="cart", direction="right")], "reasoning": " "},
    )
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [read(), unreasoned, act(steps=[FINISH]), wait_for_next_round()],
        OPERATOR_B: to_shared_bay_and_finish(),
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    refusal = act_results(result=result, agent_id=OPERATOR_A)[0]
    assert "Give one sentence of reasoning for this list. Nothing happened." in refusal
    assert actions_of(result=result, agent_id=OPERATOR_A) == []


async def test_a_round_that_ends_during_the_hold_keeps_the_list_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """operator_b sits mid-turn until the round resolves, so operator_a's list is held.

    The phase ends once operator_a's list is on the floor and operator_b has not
    read it. Only the round's end can release operator_a after that, so the test
    waits on no duration.
    """
    scenario = build(preset_name="knobs_default", overrides=BATCHED_ROUND)
    world = scenario.get_world()

    def ends_once_operator_a_is_held(phase_age: float, limit: float) -> bool:
        _ = phase_age, limit
        return world.has_unseen(agent_id=OPERATOR_B)

    def round_resolved(event: dict[str, object]) -> bool:
        return event["event_type"] == "move_a_box_round_resolved"

    scripts: dict[str, list[GatedTurn]] = {
        OPERATOR_A: [
            read(),
            act(steps=steps_along(directions=["right", "right", "up"], method="cart")),
            wait_for_next_round(),
        ],
        OPERATOR_B: [
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
        phase_timed_out=ends_once_operator_a_is_held,
    )

    [started] = result.of_type(event_type=MoveABoxRoundStarted)
    marking = started.crate_ids[CRATE_A]
    assert act_results(result=result, agent_id=OPERATOR_A) == [
        f"1. You hauled {marking} right by cart, now 21C.\n"
        f"2. You hauled {marking} right by cart, now 22C.\n"
        "Stopped after 2 of 3 actions: Hauling up from 1,3 leaves the floor. No step spent.\n"
        "Round 1 ended before the depot readout came back. "
        "Call read_notifications(wait_for='next_round')."
    ]
