"""spot_the_intersection's submit_object tool and the round verdict it drives.

Scoring is deterministic, so these assert the exact verdicts: every member must
submit, they must all submit the answer, and among correct teams the one that
said less wins. The answer itself must never reach an agent.
"""

from pathlib import Path

import pytest

from glossogen.models.event import MessageSent, RoundResultRecorded, ToolResultReceived
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.spot_the_intersection.board_certification import ObjectKind
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject, cell_label
from glossogen.scenarios.spot_the_intersection.board_rendering import render_board_line
from glossogen.scenarios.spot_the_intersection.events import IntersectionSubmissionRecorded
from glossogen.scenarios.spot_the_intersection.ids import ALREADY_SUBMITTED_MARKER
from glossogen.scenarios.spot_the_intersection.scenario import SpotTheIntersectionScenario
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn, ToolTurn
from glossogen.testing.simulation_harness import SimulationResult
from tests.scenarios.spot_the_intersection.conftest import (
    SCENARIO,
    TEAM_A,
    TEAM_B,
    TOOL,
    answer_of,
    one_round_scenario,
    play,
    say_on,
    submit,
    world_of,
)

pytestmark = pytest.mark.xdist_group(SCENARIO)


def near_miss_of(scenario: SimulationScenario) -> BoardObject:
    """A round-one object on every board but one: the strongest wrong answer."""
    round_boards = world_of(scenario=scenario).round_boards(round_number=1)
    return next(entry.obj for entry in round_boards.declared if entry.kind is ObjectKind.NEAR_MISS)


def verdict_for(result: SimulationResult, team_id: str) -> RoundResultRecorded:
    """The recorded round-one verdict of ``team_id``."""
    return next(
        verdict
        for verdict in result.of_type(event_type=RoundResultRecorded)
        if verdict.team_id == team_id and verdict.round_number == 1
    )


async def test_every_member_submitting_the_answer_gets_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = one_round_scenario()
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [submit(obj=answer), SayTurn(text="done")] for agent in TEAM_A
    }

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert verdict_for(result=result, team_id="team_a").success is True
    team_b = verdict_for(result=result, team_id="team_b")
    assert team_b.success is False
    assert team_b.reason.startswith("only 0/4 members submitted")
    recorded = result.of_type(event_type=IntersectionSubmissionRecorded)
    assert sorted(event.agent_id for event in recorded) == sorted(TEAM_A)
    assert all(event.correct for event in recorded)


async def test_a_team_one_member_short_loses_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = one_round_scenario()
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [submit(obj=answer), SayTurn(text="done")] for agent in TEAM_A[:3]
    }

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    team_a = verdict_for(result=result, team_id="team_a")
    assert team_a.success is False
    assert team_a.reason.startswith("only 3/4 members submitted")


async def test_one_member_naming_a_near_miss_sinks_the_team(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = one_round_scenario()
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [submit(obj=answer), SayTurn(text="done")] for agent in TEAM_A[:3]
    }
    scripts[TEAM_A[3]] = [submit(obj=near_miss_of(scenario=scenario)), SayTurn(text="done")]

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    team_a = verdict_for(result=result, team_id="team_a")
    assert team_a.success is False
    assert team_a.reason.startswith("members submitted different objects")


async def test_a_team_agreeing_on_a_wrong_object_loses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = one_round_scenario()
    wrong = near_miss_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [submit(obj=wrong), SayTurn(text="done")] for agent in TEAM_A
    }

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    team_a = verdict_for(result=result, team_id="team_a")
    assert team_a.success is False
    assert team_a.reason.startswith("every member submitted the same wrong object")


async def test_of_two_correct_teams_the_one_that_said_less_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = one_round_scenario()
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [submit(obj=answer), SayTurn(text="done")] for agent in TEAM_A
    }
    for agent in TEAM_B:
        scripts[agent] = [submit(obj=answer), SayTurn(text="done")]
    scripts[TEAM_B[0]] = [
        say_on(scenario=scenario, channel_id="link_b", text="found it"),
        submit(obj=answer),
        SayTurn(text="done"),
    ]

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    team_a = verdict_for(result=result, team_id="team_a")
    team_b = verdict_for(result=result, team_id="team_b")
    assert team_a.success is True
    assert team_a.reason.startswith("won")
    assert team_b.success is True
    assert team_b.reason.startswith("correct but the other team used fewer characters")


async def test_the_answer_never_reaches_an_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Submitting must not tell a viewer whether it was right, nor anyone else.

    Each viewer's own board lists the answer among its objects, so only what the
    tool returns and what the world posts are checked.
    """
    scenario = one_round_scenario()
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [submit(obj=answer), SayTurn(text="done")] for agent in TEAM_A
    }

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    answer_line = render_board_line(obj=answer)
    answer_cell = cell_label(column=answer.column, row=answer.row)
    results = [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.tool_name == TOOL
    ]
    assert results, "no submission result to check"
    world_messages = [
        event.message.text
        for event in result.of_type(event_type=MessageSent)
        if event.message.sender_agent_id not in TEAM_A + TEAM_B
    ]
    for text in results + world_messages:
        assert answer_line not in text
        assert answer_cell not in text


async def test_a_cell_off_the_grid_is_refused_and_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = one_round_scenario()
    scripts: dict[str, list[ScriptedTurn]] = {
        TEAM_A[0]: [
            ToolTurn(tool_name=TOOL, args={"shape": "star", "color": "red", "cell": "Z9"}),
            SayTurn(text="done"),
        ]
    }

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert result.of_type(event_type=IntersectionSubmissionRecorded) == []
    results = [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.tool_name == TOOL
    ]
    assert any("outside the 6x6 grid" in text for text in results), results


async def test_a_submission_cannot_be_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = one_round_scenario()
    wrong = near_miss_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        TEAM_A[0]: [
            submit(obj=wrong),
            submit(obj=answer_of(scenario=scenario)),
            SayTurn(text="done"),
        ]
    }

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    (recorded,) = result.of_type(event_type=IntersectionSubmissionRecorded)
    assert recorded.correct is False
    results = [
        event.result
        for event in result.of_type(event_type=ToolResultReceived)
        if event.tool_name == TOOL
    ]
    assert results[-1].startswith(ALREADY_SUBMITTED_MARKER)


async def test_resume_rebuilds_the_outcomes_the_live_world_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The next briefing after a resume reports the result the round really had."""
    scenario = one_round_scenario()
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent: [submit(obj=answer), SayTurn(text="done")] for agent in TEAM_A
    }
    scripts[TEAM_B[0]] = [
        say_on(scenario=scenario, channel_id="link_b", text="hello"),
        submit(obj=near_miss_of(scenario=scenario)),
        SayTurn(text="done"),
    ]
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    rebuilt = SpotTheIntersectionScenario.create_from_config(
        config=scenario.get_knobs().model_dump(mode="json")
    )

    rebuilt.restore_state_from_events(events=result.events)

    live = world_of(scenario=result.scenario)
    restored = world_of(scenario=rebuilt)
    for team_id in ("team_a", "team_b"):
        assert restored.outcome_for(team_id=team_id, round_number=1) == live.outcome_for(
            team_id=team_id, round_number=1
        )
