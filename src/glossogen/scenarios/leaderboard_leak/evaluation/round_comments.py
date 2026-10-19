"""Each round's sheets, comments and closed tasks, read back from a run's events.

The metrics and the communication views read a round through this one projection, so
they agree on which comment was written and which was shown.
"""

from typing import NamedTuple

from glossogen.models.event import SimulationEvent
from glossogen.scenarios.leaderboard_leak.events import (
    LeaderboardLeakAnswerSubmitted,
    LeaderboardLeakRoundResolved,
    LeaderboardLeakRoundStarted,
    LeaderboardLeakTaskClosed,
)


class ShownComment(NamedTuple):
    """A comment one task's log showed across teams."""

    team_id: str
    agent_id: str
    task: int
    comment: str


class LoggedRound(NamedTuple):
    """One round as its events recorded it."""

    started: LeaderboardLeakRoundStarted
    submissions: tuple[LeaderboardLeakAnswerSubmitted, ...]
    closed: tuple[LeaderboardLeakTaskClosed, ...]
    resolved: LeaderboardLeakRoundResolved | None

    def bonus_id(self, team_id: str) -> str:
        """The ID ``team_id``'s task 4 asks for."""
        for team in self.started.teams:
            if team.team_id == team_id:
                return team.task_ids[-1]
        raise KeyError(team_id)

    def value_on_sheets(self, entry_id: str) -> str:
        """The value ``entry_id`` has on whichever sheet holds it."""
        for team in self.started.teams:
            for entry in team.sheet:
                if entry.entry_id == entry_id:
                    return entry.value
        raise KeyError(entry_id)

    def shown_across_teams(self) -> list[ShownComment]:
        """Every comment a log showed to the other team, in task order."""
        shown: list[ShownComment] = []
        for closed in sorted(self.closed, key=lambda event: event.task):
            if not closed.comments_shown_across_teams:
                continue
            for team in closed.teams:
                for member in team.comments:
                    if member.comment is None:
                        continue
                    shown.append(
                        ShownComment(
                            team_id=team.team_id,
                            agent_id=member.agent_id,
                            task=closed.task,
                            comment=member.comment,
                        )
                    )
        return shown


def logged_rounds(events: list[SimulationEvent]) -> list[LoggedRound]:
    """Every round with a ``leaderboard_leak_round_started`` event, in round order."""
    started = {
        event.round_number: event
        for event in events
        if isinstance(event, LeaderboardLeakRoundStarted)
    }
    resolved = {
        event.round_number: event
        for event in events
        if isinstance(event, LeaderboardLeakRoundResolved)
    }
    return [
        LoggedRound(
            started=started[number],
            submissions=tuple(
                event
                for event in events
                if isinstance(event, LeaderboardLeakAnswerSubmitted)
                and event.round_number == number
            ),
            closed=tuple(
                event
                for event in events
                if isinstance(event, LeaderboardLeakTaskClosed) and event.round_number == number
            ),
            resolved=resolved.get(number),
        )
        for number in sorted(started)
    ]
