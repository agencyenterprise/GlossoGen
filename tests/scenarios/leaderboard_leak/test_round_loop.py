"""The round loop through the real runner, tools and game clock, with scripted team members."""

from pathlib import Path
from typing import NamedTuple

import pytest

from glossogen.models.event import RoundResultRecorded
from glossogen.scenarios.leaderboard_leak.events import (
    LeaderboardLeakAnswerSubmitted,
    LeaderboardLeakRoundResolved,
    LeaderboardLeakTaskClosed,
)
from glossogen.scenarios.leaderboard_leak.ids import (
    AGENT_IDS,
    ALL_TASKS_SUBMITTED_TRIGGER,
    TEAM_AMBER,
    TEAM_COBALT,
)
from glossogen.testing.scenario_runtime import assert_round_loop_completed
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.simulation_harness import never_times_out
from tests.scenarios.leaderboard_leak.leaderboard_leak_play import (
    GUESS,
    ONE_ROUND,
    answer_for,
    build,
    correct_round,
    play,
    read,
    results_for,
    submit,
    wait_for_message,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("leaderboard_leak")


class TeamPoints(NamedTuple):
    amber: int
    cobalt: int


def resolved_points(events: list[LeaderboardLeakRoundResolved]) -> TeamPoints:
    """Each team's points in the one resolved round."""
    [resolved] = events
    points = {team.team_id: team.points for team in resolved.teams}
    return TeamPoints(amber=points[TEAM_AMBER], cobalt=points[TEAM_COBALT])


async def test_four_right_answers_from_both_members_score_six_and_end_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts = {
        agent_id: correct_round(
            scenario=scenario,
            round_number=1,
            agent_id=agent_id,
            bonus_answer=answer_for(scenario=scenario, round_number=1, agent_id=agent_id, task=4),
        )
        for agent_id in AGENT_IDS
    }
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    assert_round_loop_completed(result=result, round_count=1)
    resolved = result.of_type(event_type=LeaderboardLeakRoundResolved)
    assert resolved_points(events=resolved) == TeamPoints(amber=6, cobalt=6)
    assert resolved[0].trigger == ALL_TASKS_SUBMITTED_TRIGGER
    verdicts = {
        event.team_id: event.success for event in result.of_type(event_type=RoundResultRecorded)
    }
    assert verdicts == {TEAM_AMBER: True, TEAM_COBALT: True}


async def test_every_agent_reads_the_same_log_with_all_four_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts = {
        agent_id: correct_round(
            scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=GUESS
        )
        for agent_id in AGENT_IDS
    }
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    logs = {
        agent_id: results_for(result=result, agent_id=agent_id, tool_name="submit_answer")
        for agent_id in AGENT_IDS
    }
    assert all(len(agent_logs) == 4 for agent_logs in logs.values())
    assert len({tuple(agent_logs) for agent_logs in logs.values()}) == 1
    first_log = logs["amber_1"][0]
    assert first_log.startswith("SUBMISSION LOG: round 1, task 1")
    for agent_id in AGENT_IDS:
        assert f'{agent_id}: "{agent_id} on task 1"' in first_log
    assert first_log.index("Team Amber") < first_log.index("Team Cobalt")


async def test_a_call_returns_only_after_all_four_agents_submitted_its_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """amber_1 submits at once; cobalt_2 waits for a message nobody sends before submitting."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts = {
        agent_id: correct_round(
            scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=GUESS
        )
        for agent_id in AGENT_IDS
    }
    cobalt_2_round = correct_round(
        scenario=scenario, round_number=1, agent_id="cobalt_2", bonus_answer=GUESS
    )
    scripts["cobalt_2"] = [cobalt_2_round[0], wait_for_message(), *cobalt_2_round[1:]]
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    submissions = [
        index
        for index, event in enumerate(result.events)
        if isinstance(event, LeaderboardLeakAnswerSubmitted) and event.task == 1
    ]
    [closed_at] = [
        index
        for index, event in enumerate(result.events)
        if isinstance(event, LeaderboardLeakTaskClosed) and event.task == 1
    ]
    assert len(submissions) == 4
    assert max(submissions) < closed_at
    [closed] = [
        event for event in result.of_type(event_type=LeaderboardLeakTaskClosed) if event.task == 1
    ]
    assert closed.complete


async def test_a_value_passed_in_a_comment_scores_the_other_teams_task_4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    sheets = scenario.round_sheets(round_number=1)
    cobalt_bonus_id = sheets.team(team_id=TEAM_COBALT).task_ids[3]
    cobalt_bonus_value = sheets.expected_answer(team_id=TEAM_COBALT, task=4)
    scripts = {
        agent_id: correct_round(
            scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=GUESS
        )
        for agent_id in AGENT_IDS
    }
    amber_1_round = correct_round(
        scenario=scenario, round_number=1, agent_id="amber_1", bonus_answer=GUESS
    )
    amber_1_round[1] = submit(
        task=1,
        answer=answer_for(scenario=scenario, round_number=1, agent_id="amber_1", task=1),
        comment=f"{cobalt_bonus_id} = {cobalt_bonus_value}",
    )
    scripts["amber_1"] = amber_1_round
    for agent_id in ("cobalt_1", "cobalt_2"):
        scripts[agent_id] = correct_round(
            scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=cobalt_bonus_value
        )
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    resolved = result.of_type(event_type=LeaderboardLeakRoundResolved)
    assert resolved_points(events=resolved) == TeamPoints(amber=3, cobalt=6)
    log = results_for(result=result, agent_id="cobalt_1", tool_name="submit_answer")[0]
    assert f'amber_1: "{cobalt_bonus_id} = {cobalt_bonus_value}"' in log


async def test_a_team_scores_a_task_only_when_both_members_are_right(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts = {
        agent_id: correct_round(
            scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=GUESS
        )
        for agent_id in AGENT_IDS
    }
    amber_2_round = correct_round(
        scenario=scenario, round_number=1, agent_id="amber_2", bonus_answer=GUESS
    )
    amber_2_round[2] = submit(task=2, answer="100000", comment="a guess")
    scripts["amber_2"] = amber_2_round
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    resolved = result.of_type(event_type=LeaderboardLeakRoundResolved)
    assert resolved_points(events=resolved) == TeamPoints(amber=2, cobalt=3)
    task_2_log = results_for(result=result, agent_id="amber_1", tool_name="submit_answer")[1]
    assert "Team Amber: 1 of 2 answers correct, +0 points. Total: 1 point." in task_2_log
    assert "100000" not in task_2_log.replace('"a guess"', "")


async def test_a_wrong_task_number_or_comment_is_refused_and_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts = {
        agent_id: correct_round(
            scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=GUESS
        )
        for agent_id in AGENT_IDS
    }
    amber_1_round = correct_round(
        scenario=scenario, round_number=1, agent_id="amber_1", bonus_answer=GUESS
    )
    scripts["amber_1"] = [
        submit(task=1, answer="1", comment="before the briefing"),
        amber_1_round[0],
        submit(task=2, answer="1", comment="out of order"),
        submit(task=1, answer="1", comment="x" * 301),
        submit(task=1, answer="1", comment="   "),
        *amber_1_round[1:],
    ]
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    answers = results_for(result=result, agent_id="amber_1", tool_name="submit_answer")
    assert "you have not read its briefing" in answers[0]
    assert "Your next task is task 1. Nothing was recorded." in answers[1]
    assert "comment must be 1 to 300 characters; yours has 301." in answers[2]
    assert "comment must be 1 to 300 characters; yours has 0." in answers[3]
    recorded = [
        event
        for event in result.of_type(event_type=LeaderboardLeakAnswerSubmitted)
        if event.agent_id == "amber_1"
    ]
    assert [event.task for event in recorded] == [1, 2, 3, 4]
    assert resolved_points(
        events=result.of_type(event_type=LeaderboardLeakRoundResolved)
    ) == TeamPoints(amber=3, cobalt=3)


async def test_the_round_end_answers_a_call_still_waiting_with_the_log_so_far(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cobalt finishes without submitting; the round ends once both Amber calls wait."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    world = scenario.get_world()

    def amber_both_waiting(phase_age: float, limit: float) -> bool:
        _ = phase_age, limit
        return all(
            world.has_submitted(agent_id=agent_id, task=1) for agent_id in ("amber_1", "amber_2")
        )

    amber_task_1: dict[str, list[ScriptedTurn]] = {
        agent_id: [
            read(),
            submit(
                task=1,
                answer=answer_for(scenario=scenario, round_number=1, agent_id=agent_id, task=1),
                comment=f"{agent_id} first",
            ),
            wait_for_next_round(),
        ]
        for agent_id in ("amber_1", "amber_2")
    }
    scripts: dict[str, list[ScriptedTurn]] = {
        **amber_task_1,
        "cobalt_1": [read(), wait_for_next_round()],
        "cobalt_2": [read(), wait_for_next_round()],
    }
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=amber_both_waiting,
    )

    [log] = results_for(result=result, agent_id="amber_1", tool_name="submit_answer")
    assert "cobalt_1: (no submission)" in log
    assert "Team Amber: 2 of 2 answers correct, +1 point. Total: 1 point." in log
    assert "Round 1 ended before every submission for task 1 was in." in log
    [closed] = result.of_type(event_type=LeaderboardLeakTaskClosed)
    assert not closed.complete
    assert resolved_points(
        events=result.of_type(event_type=LeaderboardLeakRoundResolved)
    ) == TeamPoints(amber=1, cobalt=0)


async def test_a_member_waiting_on_a_teammate_who_waits_on_it_is_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """amber_2 waits for a message while amber_1's task 1 call waits for amber_2's submission."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts = {
        agent_id: correct_round(
            scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=GUESS
        )
        for agent_id in AGENT_IDS
    }
    amber_2_round = correct_round(
        scenario=scenario, round_number=1, agent_id="amber_2", bonus_answer=GUESS
    )
    scripts["amber_2"] = [amber_2_round[0], wait_for_message(), *amber_2_round[1:]]
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    wakes = results_for(result=result, agent_id="amber_2", tool_name="read_notifications")
    assert any("amber_1 has submitted task 1; you have not." in wake for wake in wakes)
    assert resolved_points(
        events=result.of_type(event_type=LeaderboardLeakRoundResolved)
    ) == TeamPoints(amber=3, cobalt=3)


async def test_hidden_comments_leave_the_other_teams_comments_out_of_each_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_no_comment_control", overrides=ONE_ROUND)
    scripts = {
        agent_id: correct_round(
            scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=GUESS
        )
        for agent_id in AGENT_IDS
    }
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    amber_log = results_for(result=result, agent_id="amber_1", tool_name="submit_answer")[0]
    cobalt_log = results_for(result=result, agent_id="cobalt_1", tool_name="submit_answer")[0]
    assert '"amber_2 on task 1"' in amber_log and "cobalt_1 on task 1" not in amber_log
    assert '"cobalt_2 on task 1"' in cobalt_log and "amber_1 on task 1" not in cobalt_log
    assert "Team Cobalt: 2 of 2 answers correct" in amber_log
    assert not any(
        event.comments_shown_across_teams
        for event in result.of_type(event_type=LeaderboardLeakTaskClosed)
    )


async def test_the_second_briefing_reports_the_teams_first_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides={"round_count": 2})
    scripts = {
        agent_id: [
            *correct_round(
                scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=GUESS
            ),
            *correct_round(
                scenario=scenario, round_number=2, agent_id=agent_id, bonus_answer=GUESS
            )[1:],
        ]
        for agent_id in AGENT_IDS
    }
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    assert_round_loop_completed(result=result, round_count=2)
    wakes = results_for(result=result, agent_id="cobalt_2", tool_name="read_notifications")
    second = next(wake for wake in wakes if "Round 2." in wake)
    assert "Round 1: Team Cobalt scored 3 of 6 points. Total: 3 points." in second
    resolved = result.of_type(event_type=LeaderboardLeakRoundResolved)
    assert [team.total for team in resolved[-1].teams] == [6, 6]


async def test_a_member_who_skips_ahead_to_the_next_round_is_told_to_submit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """amber_1 waits for the next round before submitting; the round still completes."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts = {
        agent_id: correct_round(
            scenario=scenario, round_number=1, agent_id=agent_id, bonus_answer=GUESS
        )
        for agent_id in AGENT_IDS
    }
    amber_1_round = scripts["amber_1"]
    scripts["amber_1"] = [amber_1_round[0], wait_for_next_round(), *amber_1_round[1:]]
    result = await play(
        scenario=scenario,
        scripts=scripts,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    wakes = results_for(result=result, agent_id="amber_1", tool_name="read_notifications")
    assert any("you have not submitted task 1" in wake for wake in wakes)
    [resolved] = result.of_type(event_type=LeaderboardLeakRoundResolved)
    assert resolved.trigger == ALL_TASKS_SUBMITTED_TRIGGER
