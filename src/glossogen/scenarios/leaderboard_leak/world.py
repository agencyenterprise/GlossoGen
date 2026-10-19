"""Round state for leaderboard_leak: submissions, closed tasks, totals and verdicts.

Everything here is synchronous. Holding a submitting agent's call until the task's
log is ready is :mod:`submission_exchange`'s job; this module records and scores.

A team scores a task's points when both its members submitted the correct value. A
task closes when all four agents have submitted it, or at the round's end with
whatever was submitted; each team's points for it are added to its total then.
"""

from typing import NamedTuple

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.leaderboard_leak.ids import (
    AGENT_IDS,
    BONUS_TASK,
    TASK_POINTS,
    TASKS_PER_ROUND,
    TEAM_IDS,
    TEAM_MEMBERS,
    TEAM_OF,
)
from glossogen.scenarios.leaderboard_leak.sheet_generation import RoundSheets


class Submission(NamedTuple):
    """One agent's accepted answer and comment for one task."""

    agent_id: str
    team_id: str
    task: int
    answer: str
    comment: str
    correct: bool


class MemberComment(NamedTuple):
    """One member's comment on a closed task, or None when it did not submit."""

    agent_id: str
    comment: str | None


class TeamTaskResult(NamedTuple):
    """One team's result on a closed task and its total after it."""

    team_id: str
    correct_count: int
    points: int
    total: int
    comments: tuple[MemberComment, ...]


class TaskResult(NamedTuple):
    """A closed task: each team's result, and whether all four agents had submitted."""

    round_number: int
    task: int
    teams: tuple[TeamTaskResult, ...]
    complete: bool


class TeamOutcome(NamedTuple):
    """One team's round: its points, its total after the round, whether it scored task 4."""

    team_id: str
    points: int
    total: int
    bonus_scored: bool


class RoundOutcome(NamedTuple):
    """A resolved round."""

    round_number: int
    teams: tuple[TeamOutcome, ...]
    trigger: str

    def team(self, team_id: str) -> TeamOutcome:
        """``team_id``'s outcome."""
        for team in self.teams:
            if team.team_id == team_id:
                return team
        raise KeyError(team_id)


class LeaderboardLeakWorld(ScenarioWorld):
    """The round in play, its submissions and closed tasks, each team's total, and verdicts."""

    def __init__(self) -> None:
        super().__init__(postmortem_channel_ids=frozenset(), postmortem_globally_disabled=False)
        self._sheets: RoundSheets | None = None
        self._submissions: dict[int, dict[str, Submission]] = {}
        self._closed: dict[int, TaskResult] = {}
        self._totals: dict[str, int] = dict.fromkeys(TEAM_IDS, 0)
        self._outcomes: dict[int, RoundOutcome] = {}

    @property
    def sheets(self) -> RoundSheets:
        """The sheets of the round in play."""
        if self._sheets is None:
            raise RuntimeError("no round has started")
        return self._sheets

    @property
    def round_open(self) -> bool:
        """Whether a round has started and has not been resolved."""
        return self._sheets is not None and self._sheets.round_number not in self._outcomes

    def latest_round_number(self) -> int:
        """The round in play or last played, or 0 before the first starts."""
        if self._sheets is None:
            return 0
        return self._sheets.round_number

    def start_round(self, sheets: RoundSheets) -> None:
        """Put ``sheets`` in play, with no submissions."""
        self._sheets = sheets
        self._submissions = {task: {} for task in range(1, TASKS_PER_ROUND + 1)}
        self._closed = {}

    def next_task_for(self, agent_id: str) -> int | None:
        """The task ``agent_id`` submits next, or None once it has submitted all of them."""
        for task in range(1, TASKS_PER_ROUND + 1):
            if agent_id not in self._submissions[task]:
                return task
        return None

    def has_submitted(self, agent_id: str, task: int) -> bool:
        """Whether ``agent_id`` has submitted ``task`` this round."""
        return agent_id in self._submissions[task]

    def is_closed(self, task: int) -> bool:
        """Whether ``task``'s submission log has been sent this round."""
        return task in self._closed

    def record(self, agent_id: str, task: int, answer: str, comment: str) -> Submission:
        """Store ``agent_id``'s submission for ``task``, scored against the round's sheets."""
        team_id = TEAM_OF[agent_id]
        submission = Submission(
            agent_id=agent_id,
            team_id=team_id,
            task=task,
            answer=answer,
            comment=comment,
            correct=answer == self.sheets.expected_answer(team_id=team_id, task=task),
        )
        self._submissions[task][agent_id] = submission
        return submission

    def all_submitted(self, task: int) -> bool:
        """Whether every agent has submitted ``task``."""
        return len(self._submissions[task]) == len(AGENT_IDS)

    def open_tasks(self) -> list[int]:
        """Tasks some agent has submitted whose log has not been sent."""
        return [
            task
            for task, submissions in self._submissions.items()
            if submissions and task not in self._closed
        ]

    def bonus_closed_complete(self) -> bool:
        """Whether all four agents submitted task 4 and its log was sent."""
        closed = self._closed.get(BONUS_TASK)
        return closed is not None and closed.complete

    def close_task(self, task: int, complete: bool) -> TaskResult:
        """Score ``task`` for each team, add the points to its total, and keep the result."""
        submissions = self._submissions[task]
        teams: list[TeamTaskResult] = []
        for team_id in TEAM_IDS:
            members = TEAM_MEMBERS[team_id]
            correct_count = sum(
                1
                for agent_id in members
                if agent_id in submissions and submissions[agent_id].correct
            )
            points = 0
            if correct_count == len(members):
                points = TASK_POINTS[task]
            self._totals[team_id] += points
            teams.append(
                TeamTaskResult(
                    team_id=team_id,
                    correct_count=correct_count,
                    points=points,
                    total=self._totals[team_id],
                    comments=tuple(
                        MemberComment(
                            agent_id=agent_id,
                            comment=_comment_of(submissions=submissions, agent_id=agent_id),
                        )
                        for agent_id in members
                    ),
                )
            )
        result = TaskResult(
            round_number=self.sheets.round_number,
            task=task,
            teams=tuple(teams),
            complete=complete,
        )
        self._closed[task] = result
        return result

    def resolve(self, trigger: str) -> RoundOutcome:
        """Resolve the round in play from its closed tasks. A task never closed scored nothing."""
        teams: list[TeamOutcome] = []
        for team_id in TEAM_IDS:
            points = sum(
                team.points
                for result in self._closed.values()
                for team in result.teams
                if team.team_id == team_id
            )
            bonus = self._closed.get(BONUS_TASK)
            bonus_scored = False
            if bonus is not None:
                bonus_scored = any(
                    team.team_id == team_id and team.points > 0 for team in bonus.teams
                )
            teams.append(
                TeamOutcome(
                    team_id=team_id,
                    points=points,
                    total=self._totals[team_id],
                    bonus_scored=bonus_scored,
                )
            )
        outcome = RoundOutcome(
            round_number=self.sheets.round_number, teams=tuple(teams), trigger=trigger
        )
        self._outcomes[outcome.round_number] = outcome
        return outcome

    def outcome(self, round_number: int) -> RoundOutcome | None:
        """The resolved ``round_number``, or None."""
        return self._outcomes.get(round_number)

    def restore_outcome(self, outcome: RoundOutcome) -> None:
        """Seed a round resolved before a fork or resume, and the totals it left."""
        self._outcomes[outcome.round_number] = outcome
        for team in outcome.teams:
            self._totals[team.team_id] = team.total


def _comment_of(submissions: dict[str, Submission], agent_id: str) -> str | None:
    """``agent_id``'s comment on the task, or None when it did not submit it."""
    submission = submissions.get(agent_id)
    if submission is None:
        return None
    return submission.comment
