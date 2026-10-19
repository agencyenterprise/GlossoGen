"""leaderboard_leak's events: each round's sheets, every submission, each closed task,
and the round's verdict."""

from typing import Literal

from pydantic import BaseModel

from glossogen.models.event_base import EventBase


class SheetEntryRecord(BaseModel):
    """One line of a sheet as the briefing listed it."""

    entry_id: str
    value: str


class TeamRoundRecord(BaseModel):
    """One team's sheet, in briefing order, and the ID each of its tasks asks for."""

    team_id: str
    sheet: list[SheetEntryRecord]
    task_ids: list[str]


class LeaderboardLeakRoundStarted(EventBase):
    """Both teams' sheets and tasks for the round."""

    event_type: Literal["leaderboard_leak_round_started"] = "leaderboard_leak_round_started"
    teams: list[TeamRoundRecord]


class LeaderboardLeakAnswerSubmitted(EventBase):
    """One agent's accepted submission for one task."""

    event_type: Literal["leaderboard_leak_answer_submitted"] = "leaderboard_leak_answer_submitted"
    agent_id: str
    team_id: str
    task: int
    answer: str
    comment: str
    correct: bool


class MemberCommentRecord(BaseModel):
    """One agent's comment on a task, or None when it did not submit before the task closed."""

    agent_id: str
    comment: str | None


class TeamTaskRecord(BaseModel):
    """One team's result on a closed task, as the submission log reported it."""

    team_id: str
    correct_count: int
    points: int
    total: int
    comments: list[MemberCommentRecord]


class LeaderboardLeakTaskClosed(EventBase):
    """A task's submission log was sent.

    ``complete`` is false when the round ended before all four agents submitted.
    ``comments_shown_across_teams`` is whether each team's log held the other team's
    comments.
    """

    event_type: Literal["leaderboard_leak_task_closed"] = "leaderboard_leak_task_closed"
    task: int
    teams: list[TeamTaskRecord]
    complete: bool
    comments_shown_across_teams: bool


class TeamRoundResult(BaseModel):
    """One team's points for the round, its total after it, and whether it scored task 4."""

    team_id: str
    points: int
    total: int
    bonus_scored: bool


class LeaderboardLeakRoundResolved(EventBase):
    """Each team's result for the round and the trigger that ended it."""

    event_type: Literal["leaderboard_leak_round_resolved"] = "leaderboard_leak_round_resolved"
    teams: list[TeamRoundResult]
    trigger: str
