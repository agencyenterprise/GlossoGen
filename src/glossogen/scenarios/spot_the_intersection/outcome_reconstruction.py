"""Rebuild per-team round state from a recorded event log on resume.

Used on resume, fork and replace-agent. Reads ``SpotTheIntersectionRoundStarted``
for each round's answer as recorded, ``IntersectionSubmissionRecorded`` for each
member's submission and its team's character count at that moment,
``MessageSent`` on each team's link for a team that never locked, and
``RoundEnded`` for which rounds finished.

A finished round is scored through :func:`score_round`, the rule the live world
applies, so the next round's briefing reports the right previous result. A round
that started and never ended is the one the run stopped in; its submissions and
character counts are returned so the resumed round continues from them rather
than from nothing. Every round whose start the log holds is returned too, so a
resume that reopens one does not record its start again.

The answer comes from the log rather than from regenerating the round, so a run
recorded before a change to board generation is still scored on the boards it
played.
"""

from collections.abc import Sequence
from typing import Any, NamedTuple

from glossogen.engine.round_outcome_log import RoundOutcomeLog
from glossogen.models.event import MessageSent, RoundEnded
from glossogen.scenarios.spot_the_intersection.board_model import BoardObject
from glossogen.scenarios.spot_the_intersection.board_rendering import (
    parse_board_line,
    parse_cell_label,
)
from glossogen.scenarios.spot_the_intersection.events import (
    IntersectionSubmissionRecorded,
    SpotTheIntersectionRoundStarted,
)
from glossogen.scenarios.spot_the_intersection.world_state import (
    IntersectionOutcome,
    SimulatedOpponent,
    TeamSnapshot,
    TeamState,
    score_round,
    snapshot_from_submissions,
)


class TeamInProgress(NamedTuple):
    """One team's state partway through a round: who submitted what, and its spend."""

    team_id: str
    submissions_by_agent: dict[str, BoardObject]
    characters: int


class RoundInProgress(NamedTuple):
    """The round a recorded run stopped in, team by team."""

    round_number: int
    teams: tuple[TeamInProgress, ...]


class RestoredRounds(NamedTuple):
    """What a resume carries forward beyond the outcomes it records.

    ``started_rounds`` are the rounds whose start the log already holds, ended
    or not. ``in_progress`` is the round the log stopped in, if one never ended.
    """

    started_rounds: frozenset[int]
    in_progress: RoundInProgress | None


class _RecordedRounds(NamedTuple):
    """What a log records per round, read in one pass."""

    started: dict[int, SpotTheIntersectionRoundStarted]
    submissions: dict[int, dict[str, list[IntersectionSubmissionRecorded]]]
    unlocked_characters: dict[int, dict[str, int]]
    ended: set[int]


def restore_rounds_from_events(
    teams: dict[str, TeamState],
    outcome_log: RoundOutcomeLog[IntersectionOutcome],
    competitive: bool,
    simulated_opponent: SimulatedOpponent | None,
    budget: int,
    events: list[Any],
) -> RestoredRounds:
    """Record an outcome for every round ``events`` shows finished.

    Returns the rounds whose start the log holds and the state of the round it
    stopped in. Raises ``ValueError`` for a finished round whose start was never
    recorded, since there is then no answer to score it against.
    """
    recorded = _read_rounds(teams=teams, events=events)
    for round_number in sorted(recorded.ended):
        if any(
            outcome_log.recorded_for(team_id=team_id, round_number=round_number) is not None
            for team_id in teams
        ):
            continue
        round_started = recorded.started.get(round_number)
        if round_started is None:
            raise ValueError(f"round {round_number} ended but its start was never recorded")
        snapshots = [
            _snapshot(
                team=team,
                round_started=round_started,
                submissions=recorded.submissions.get(round_number, {}).get(team_id, []),
                unlocked_characters=recorded.unlocked_characters.get(round_number, {}).get(
                    team_id, 0
                ),
                budget=budget,
            )
            for team_id, team in teams.items()
        ]
        for outcome in score_round(
            round_number=round_number,
            snapshots=snapshots,
            competitive=competitive,
            simulated_opponent=simulated_opponent,
        ):
            outcome_log.record(team_id=outcome.team_id, round_number=round_number, outcome=outcome)
    return RestoredRounds(
        started_rounds=frozenset(recorded.started),
        in_progress=_round_in_progress(teams=teams, recorded=recorded),
    )


def _read_rounds(teams: dict[str, TeamState], events: list[Any]) -> _RecordedRounds:
    """Index the log's round starts, submissions, link spend and round ends."""
    team_id_by_link = {team.link_channel_id: team.team_id for team in teams.values()}
    members = {team.team_id: frozenset(team.member_agent_ids) for team in teams.values()}
    recorded = _RecordedRounds(started={}, submissions={}, unlocked_characters={}, ended=set())
    for event in events:
        if isinstance(event, SpotTheIntersectionRoundStarted):
            recorded.started[event.round_number] = event
        elif isinstance(event, IntersectionSubmissionRecorded):
            by_team = recorded.submissions.setdefault(event.round_number, {})
            by_team.setdefault(event.team_id, []).append(event)
        elif isinstance(event, MessageSent):
            team_id = team_id_by_link.get(event.message.channel_id)
            # The world's own notices on a link are not metered live either.
            if team_id is not None and event.message.sender_agent_id in members[team_id]:
                by_team = recorded.unlocked_characters.setdefault(event.round_number, {})
                by_team[team_id] = by_team.get(team_id, 0) + len(event.message.text)
        elif isinstance(event, RoundEnded):
            recorded.ended.add(event.round_number)
    return recorded


def _round_in_progress(
    teams: dict[str, TeamState], recorded: _RecordedRounds
) -> RoundInProgress | None:
    """The latest round the log started and never ended, if there is one."""
    unfinished = [number for number in recorded.started if number not in recorded.ended]
    if not unfinished:
        return None
    round_number = max(unfinished)
    round_started = recorded.started[round_number]
    in_progress: list[TeamInProgress] = []
    for team_id, team in teams.items():
        submissions = recorded.submissions.get(round_number, {}).get(team_id, [])
        in_progress.append(
            TeamInProgress(
                team_id=team_id,
                submissions_by_agent={
                    submission.agent_id: _submitted_object(
                        submission=submission, grid_size=round_started.grid_size
                    )
                    for submission in submissions
                },
                characters=_team_characters(
                    team=team,
                    submissions=submissions,
                    unlocked_characters=recorded.unlocked_characters.get(round_number, {}).get(
                        team_id, 0
                    ),
                ),
            )
        )
    return RoundInProgress(round_number=round_number, teams=tuple(in_progress))


def _team_characters(
    team: TeamState,
    submissions: Sequence[IntersectionSubmissionRecorded],
    unlocked_characters: int,
) -> int:
    """What a team was charged in a round, from its recorded events.

    A team that locked is charged the count on its last submission, the latch
    the live world applied; one that did not is charged every link character.
    """
    if len(submissions) == team.members_required:
        return max(submission.team_characters for submission in submissions)
    return unlocked_characters


def _snapshot(
    team: TeamState,
    round_started: SpotTheIntersectionRoundStarted,
    submissions: Sequence[IntersectionSubmissionRecorded],
    unlocked_characters: int,
    budget: int,
) -> TeamSnapshot:
    """One team's scoring state for a finished round, from its recorded events."""
    characters = _team_characters(
        team=team, submissions=submissions, unlocked_characters=unlocked_characters
    )
    objects = [
        _submitted_object(submission=submission, grid_size=round_started.grid_size)
        for submission in submissions
    ]
    return snapshot_from_submissions(
        team_id=team.team_id,
        members_required=team.members_required,
        submissions=objects,
        answer=parse_board_line(line=round_started.answer_line, grid_size=round_started.grid_size),
        budget_exceeded=budget > 0 and characters >= budget,
        characters=characters,
    )


def _submitted_object(submission: IntersectionSubmissionRecorded, grid_size: int) -> BoardObject:
    """The object a recorded submission named."""
    column, row = parse_cell_label(label=submission.cell, grid_size=grid_size)
    return BoardObject(shape=submission.shape, color=submission.color, column=column, row=row)
