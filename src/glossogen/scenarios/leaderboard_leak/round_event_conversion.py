"""Between the scenario's round state and the events that record it."""

from glossogen.scenarios.leaderboard_leak.events import (
    LeaderboardLeakRoundResolved,
    LeaderboardLeakRoundStarted,
    LeaderboardLeakTaskClosed,
    MemberCommentRecord,
    SheetEntryRecord,
    TeamRoundRecord,
    TeamRoundResult,
    TeamTaskRecord,
)
from glossogen.scenarios.leaderboard_leak.sheet_generation import (
    RoundSheets,
    SheetEntry,
    TeamRound,
)
from glossogen.scenarios.leaderboard_leak.world import RoundOutcome, TaskResult, TeamOutcome


def round_started_event(sheets: RoundSheets) -> LeaderboardLeakRoundStarted:
    """The event recording ``sheets``."""
    return LeaderboardLeakRoundStarted(
        round_number=sheets.round_number,
        teams=[
            TeamRoundRecord(
                team_id=team.team_id,
                sheet=[
                    SheetEntryRecord(entry_id=entry.entry_id, value=entry.value)
                    for entry in team.sheet
                ],
                task_ids=list(team.task_ids),
            )
            for team in sheets.teams
        ],
    )


def sheets_from_event(event: LeaderboardLeakRoundStarted) -> RoundSheets:
    """The sheets a logged round was played with."""
    return RoundSheets(
        round_number=event.round_number,
        teams=tuple(
            TeamRound(
                team_id=team.team_id,
                sheet=tuple(
                    SheetEntry(entry_id=entry.entry_id, value=entry.value) for entry in team.sheet
                ),
                task_ids=tuple(team.task_ids),
            )
            for team in event.teams
        ),
    )


def task_closed_event(
    result: TaskResult, comments_shown_across_teams: bool
) -> LeaderboardLeakTaskClosed:
    """The event recording a closed task's log."""
    return LeaderboardLeakTaskClosed(
        round_number=result.round_number,
        task=result.task,
        teams=[
            TeamTaskRecord(
                team_id=team.team_id,
                correct_count=team.correct_count,
                points=team.points,
                total=team.total,
                comments=[
                    MemberCommentRecord(agent_id=member.agent_id, comment=member.comment)
                    for member in team.comments
                ],
            )
            for team in result.teams
        ],
        complete=result.complete,
        comments_shown_across_teams=comments_shown_across_teams,
    )


def round_resolved_event(outcome: RoundOutcome) -> LeaderboardLeakRoundResolved:
    """The event recording a resolved round."""
    return LeaderboardLeakRoundResolved(
        round_number=outcome.round_number,
        teams=[
            TeamRoundResult(
                team_id=team.team_id,
                points=team.points,
                total=team.total,
                bonus_scored=team.bonus_scored,
            )
            for team in outcome.teams
        ],
        trigger=outcome.trigger,
    )


def outcome_from_event(event: LeaderboardLeakRoundResolved) -> RoundOutcome:
    """The outcome a logged round was resolved with."""
    return RoundOutcome(
        round_number=event.round_number,
        teams=tuple(
            TeamOutcome(
                team_id=team.team_id,
                points=team.points,
                total=team.total,
                bonus_scored=team.bonus_scored,
            )
            for team in event.teams
        ),
        trigger=event.trigger,
    )
