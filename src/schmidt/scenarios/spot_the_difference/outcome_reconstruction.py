"""Rebuild per-team ``DiffOutcome`` entries from a JSONL event list.

Used on resume / fork / replace-agent to seed the world's outcome history so
the next-round injection can render an accurate "previous round" block. The
reconstructor reads ``SpotTheDifferenceCaseStarted`` for each round's K,
``DifferenceSubmissionJudged`` for each team's locked verdict, ``MessageSent``
on the link channels to recover characters for any team that never submitted,
and ``RoundEnded`` to know which rounds are complete.
"""

from typing import Any

from schmidt.models.event import MessageSent, RoundEnded
from schmidt.scenarios.spot_the_difference.events import (
    DifferenceSubmissionJudged,
    SpotTheDifferenceCaseStarted,
)
from schmidt.scenarios.spot_the_difference.scene_generation import DiffCase
from schmidt.scenarios.spot_the_difference.team_routing import team_id_for_channel
from schmidt.scenarios.spot_the_difference.world_state import (
    SubmissionSnapshot,
    TeamState,
    build_round_outcomes,
)


def restore_outcomes_from_events(
    teams: dict[str, TeamState],
    cases: list[DiffCase],
    two_teams: bool,
    events: list[Any],
) -> None:
    """Append a ``DiffOutcome`` to each team for every completed round in ``events``."""
    difference_count_by_round: dict[int, int] = {}
    budget_by_round: dict[int, int] = {}
    judged_by_round_team: dict[int, dict[str, DifferenceSubmissionJudged]] = {}
    characters_by_round_team: dict[int, dict[str, int]] = {}
    completed_rounds: set[int] = set()
    for event in events:
        round_number = getattr(event, "round_number", None)
        if not isinstance(round_number, int) or round_number < 1:
            continue
        if isinstance(event, SpotTheDifferenceCaseStarted):
            difference_count_by_round[round_number] = event.difference_count
            budget_by_round[round_number] = event.round_time_budget_seconds
        elif isinstance(event, DifferenceSubmissionJudged):
            judged_by_round_team.setdefault(round_number, {})[event.team_id] = event
        elif isinstance(event, MessageSent):
            message_team_id = team_id_for_channel(channel_id=event.message.channel_id)
            if message_team_id is None:
                continue
            bucket = characters_by_round_team.setdefault(round_number, {})
            bucket[message_team_id] = bucket.get(message_team_id, 0) + len(event.message.text)
        elif isinstance(event, RoundEnded):
            completed_rounds.add(round_number)
    for round_number in sorted(completed_rounds):
        if round_number > len(cases):
            continue
        if any(
            any(outcome.case_number == round_number for outcome in team.outcomes)
            for team in teams.values()
        ):
            continue
        budget = budget_by_round.get(round_number)
        if budget is None:
            budget = cases[round_number - 1].round_time_budget_seconds
        snapshots = _snapshots_for_round(
            team_ids=list(teams.keys()),
            judged=judged_by_round_team.get(round_number, {}),
            characters=characters_by_round_team.get(round_number, {}),
            budget=budget,
        )
        total_differences = difference_count_by_round.get(
            round_number, cases[round_number - 1].difference_count
        )
        outcomes = build_round_outcomes(
            case_number=round_number,
            total_differences=total_differences,
            two_teams=two_teams,
            snapshots=snapshots,
        )
        for team_id, team in teams.items():
            team.outcomes.append(outcomes[team_id])
            team.round_outcome_marked = True


def _snapshots_for_round(
    team_ids: list[str],
    judged: dict[str, DifferenceSubmissionJudged],
    characters: dict[str, int],
    budget: int,
) -> dict[str, SubmissionSnapshot]:
    """Build each team's submission snapshot for one completed round.

    A submitted team's characters are the value latched at submission; a team
    that never submitted is charged its total link-channel characters. Either
    way ``budget_exceeded`` is the relevant character count reaching ``budget``.
    """
    snapshots: dict[str, SubmissionSnapshot] = {}
    for team_id in team_ids:
        event = judged.get(team_id)
        if event is None:
            total = characters.get(team_id, 0)
            snapshots[team_id] = SubmissionSnapshot(
                submitted=False,
                found_all=False,
                false_positive_count=0,
                found_count=0,
                budget_exceeded=total >= budget,
                characters=total,
            )
            continue
        snapshots[team_id] = SubmissionSnapshot(
            submitted=True,
            found_all=event.found_all,
            false_positive_count=event.false_positive_count,
            found_count=len(set(event.matched_difference_indices)),
            budget_exceeded=event.characters_at_submission >= budget,
            characters=event.characters_at_submission,
        )
    return snapshots
