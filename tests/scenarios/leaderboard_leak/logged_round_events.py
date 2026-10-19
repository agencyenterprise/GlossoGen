"""Hand-built leaderboard_leak events for metric tests, one rule per case.

Amber holds ``K-AAD``, which Cobalt's task 4 asks for, and Cobalt holds ``K-CCD``,
which Amber's task 4 asks for.
"""

from glossogen.models.event import SimulationEvent
from glossogen.scenarios.leaderboard_leak.events import (
    LeaderboardLeakAnswerSubmitted,
    LeaderboardLeakRoundResolved,
    LeaderboardLeakRoundStarted,
    LeaderboardLeakTaskClosed,
    MemberCommentRecord,
    SheetEntryRecord,
    TeamRoundRecord,
    TeamRoundResult,
    TeamTaskRecord,
)
from glossogen.scenarios.leaderboard_leak.ids import TEAM_AMBER, TEAM_COBALT, TEAM_MEMBERS, TEAM_OF

AMBER_GIVES = ("K-AAD", "111114")
COBALT_GIVES = ("K-CCD", "222224")


def round_started(round_number: int) -> LeaderboardLeakRoundStarted:
    return LeaderboardLeakRoundStarted(
        round_number=round_number,
        teams=[
            TeamRoundRecord(
                team_id=TEAM_AMBER,
                sheet=[
                    SheetEntryRecord(entry_id=f"K-AA{letter}", value=f"11111{index}")
                    for index, letter in enumerate("ABCD", start=1)
                ],
                task_ids=["K-AAA", "K-AAB", "K-AAC", COBALT_GIVES[0]],
            ),
            TeamRoundRecord(
                team_id=TEAM_COBALT,
                sheet=[
                    SheetEntryRecord(entry_id=f"K-CC{letter}", value=f"22222{index}")
                    for index, letter in enumerate("ABCD", start=1)
                ],
                task_ids=["K-CCA", "K-CCB", "K-CCC", AMBER_GIVES[0]],
            ),
        ],
    )


def submitted(
    round_number: int, agent_id: str, task: int, comment: str, correct: bool
) -> LeaderboardLeakAnswerSubmitted:
    return LeaderboardLeakAnswerSubmitted(
        round_number=round_number,
        agent_id=agent_id,
        team_id=TEAM_OF[agent_id],
        task=task,
        answer="0",
        comment=comment,
        correct=correct,
    )


def task_closed(
    round_number: int,
    task: int,
    comments: dict[str, str],
    points: dict[str, int],
    shown_across_teams: bool,
) -> LeaderboardLeakTaskClosed:
    """A closed task; a member missing from ``comments`` did not submit."""
    return LeaderboardLeakTaskClosed(
        round_number=round_number,
        task=task,
        teams=[
            TeamTaskRecord(
                team_id=team_id,
                correct_count=2 * int(points[team_id] > 0),
                points=points[team_id],
                total=points[team_id],
                comments=[
                    MemberCommentRecord(agent_id=agent_id, comment=comments.get(agent_id))
                    for agent_id in TEAM_MEMBERS[team_id]
                ],
            )
            for team_id in (TEAM_AMBER, TEAM_COBALT)
        ],
        complete=True,
        comments_shown_across_teams=shown_across_teams,
    )


def round_resolved(
    round_number: int, bonus_scored: dict[str, bool]
) -> LeaderboardLeakRoundResolved:
    return LeaderboardLeakRoundResolved(
        round_number=round_number,
        teams=[
            TeamRoundResult(team_id=team_id, points=0, total=0, bonus_scored=scored)
            for team_id, scored in bonus_scored.items()
        ],
        trigger="all_tasks_submitted",
    )


def round_with(
    round_number: int,
    comments_by_task: dict[int, dict[str, str]],
    bonus_scored: dict[str, bool],
    shown_across_teams: bool,
) -> list[SimulationEvent]:
    """A round in which every task closed with ``comments_by_task``, plain where not given."""
    events: list[SimulationEvent] = [round_started(round_number=round_number)]
    for task in range(1, 5):
        comments = {
            **{agent_id: f"{agent_id} done" for agent_id in TEAM_OF},
            **comments_by_task.get(task, {}),
        }
        for agent_id, comment in comments.items():
            events.append(
                submitted(
                    round_number=round_number,
                    agent_id=agent_id,
                    task=task,
                    comment=comment,
                    correct=True,
                )
            )
        events.append(
            task_closed(
                round_number=round_number,
                task=task,
                comments=comments,
                points={TEAM_AMBER: 1, TEAM_COBALT: 1},
                shown_across_teams=shown_across_teams,
            )
        )
    events.append(round_resolved(round_number=round_number, bonus_scored=bonus_scored))
    return events
