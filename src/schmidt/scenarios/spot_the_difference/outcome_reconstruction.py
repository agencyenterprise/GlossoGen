"""Rebuild per-team ``DiffOutcome`` entries from a JSONL event list.

Used on resume / fork / replace-agent to seed the world's outcome history so
the next-round injection can render an accurate "previous round" block. The
reconstructor reads ``SpotTheDifferenceCaseStarted`` for each round's K,
``DifferenceSubmissionJudged`` for each member's locked answer (two per team
under ``all_must_submit``), ``MessageSent`` on the link channels to recover
characters for any team that never locked, and ``RoundEnded`` to know which
rounds are complete.
"""

from typing import Any

from schmidt.models.event import MessageSent, RoundEnded
from schmidt.scenarios.spot_the_difference.difference_judge import combine_team_verdict
from schmidt.scenarios.spot_the_difference.events import (
    DifferenceSubmissionJudged,
    SpotTheDifferenceCaseStarted,
)
from schmidt.scenarios.spot_the_difference.scene_generation import DiffCase
from schmidt.scenarios.spot_the_difference.team_routing import team_id_for_link_message
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
    judged_by_round_team: dict[int, dict[str, list[DifferenceSubmissionJudged]]] = {}
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
            team_bucket = judged_by_round_team.setdefault(round_number, {})
            team_bucket.setdefault(event.team_id, []).append(event)
        elif isinstance(event, MessageSent):
            message_team_id = team_id_for_link_message(
                agent_id=event.message.sender_agent_id, channel_id=event.message.channel_id
            )
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
        total_differences = difference_count_by_round.get(round_number)
        if total_differences is None:
            total_differences = cases[round_number - 1].difference_count
        snapshots = _snapshots_for_round(
            teams=teams,
            total_differences=total_differences,
            judged=judged_by_round_team.get(round_number, {}),
            characters=characters_by_round_team.get(round_number, {}),
            budget=budget,
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
    teams: dict[str, TeamState],
    total_differences: int,
    judged: dict[str, list[DifferenceSubmissionJudged]],
    characters: dict[str, int],
    budget: int,
) -> dict[str, SubmissionSnapshot]:
    """Build each team's submission snapshot for one completed round.

    A team that met its submission requirement is scored from the combined
    member verdicts and the characters latched at lock; a team that did not
    (no submission, or only one member under ``all_must_submit``) is charged its
    total link-channel characters and marked not-submitted.
    """
    snapshots: dict[str, SubmissionSnapshot] = {}
    for team_id, team in teams.items():
        member_events = judged.get(team_id, [])
        members_submitted = len(member_events)
        members_required = team.members_required
        if members_submitted < members_required:
            total = characters.get(team_id, 0)
            snapshots[team_id] = SubmissionSnapshot(
                submitted=False,
                found_all=False,
                false_positive_count=0,
                found_count=0,
                budget_exceeded=budget > 0 and total >= budget,
                characters=total,
                members_submitted=members_submitted,
                members_required=members_required,
                agreed=True,
            )
            continue
        verdict = combine_team_verdict(
            matched_sets=[set(event.matched_difference_indices) for event in member_events],
            false_positive_counts=[event.false_positive_count for event in member_events],
            total_differences=total_differences,
        )
        latched_characters = max(event.characters_at_submission for event in member_events)
        snapshots[team_id] = SubmissionSnapshot(
            submitted=True,
            found_all=verdict.found_all,
            false_positive_count=verdict.false_positive_count,
            found_count=verdict.found_count,
            budget_exceeded=budget > 0 and latched_characters >= budget,
            characters=latched_characters,
            members_submitted=members_submitted,
            members_required=members_required,
            agreed=verdict.agreed,
        )
    return snapshots
