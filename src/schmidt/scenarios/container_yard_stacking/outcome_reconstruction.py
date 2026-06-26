"""Rebuild per-team ``YardOutcome`` entries from a JSONL event list.

Used on resume / fork / replace-agent to seed the world's outcome history
so the next-round injection can render an accurate "previous round" block.
The reconstructor walks ``ContainerYardMoveJudged`` events to decide which
batch containers were placed, ``MessageSent`` events on the link channels to
recover each team's character usage, and ``RoundEnded`` events to know which
rounds are complete.
"""

from typing import Any

from schmidt.models.event import MessageSent, RoundEnded
from schmidt.scenarios.container_yard_stacking.case_rendering import render_container
from schmidt.scenarios.container_yard_stacking.events import ContainerYardMoveJudged
from schmidt.scenarios.container_yard_stacking.ids import TEAM_SOLO_ID
from schmidt.scenarios.container_yard_stacking.team_routing import (
    AGENT_ID_TO_TEAM_ID,
    team_id_for_channel,
)
from schmidt.scenarios.container_yard_stacking.world_state import (
    StepOutcome,
    TeamState,
    YardOutcome,
)
from schmidt.scenarios.container_yard_stacking.yard_cases import YardCase


def restore_outcomes_from_events(
    teams: dict[str, TeamState],
    cases: list[YardCase],
    two_teams: bool,
    events: list[Any],
) -> None:
    """Append a ``YardOutcome`` to each team for every completed round in ``events``."""
    moves_by_round_team: dict[int, dict[str, list[ContainerYardMoveJudged]]] = {}
    characters_by_round_team: dict[int, dict[str, int]] = {}
    completed_rounds: set[int] = set()
    for event in events:
        round_number = getattr(event, "round_number", None)
        if not isinstance(round_number, int) or round_number < 1:
            continue
        if isinstance(event, ContainerYardMoveJudged):
            team_id = _team_id_for_agent(agent_id=event.agent_id, two_teams=two_teams)
            moves_by_round_team.setdefault(round_number, {}).setdefault(team_id, []).append(event)
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
        for team_id, team in teams.items():
            if any(outcome.case_number == round_number for outcome in team.outcomes):
                continue
            team.outcomes.append(
                _reconstruct_outcome(
                    case=cases[round_number - 1],
                    round_number=round_number,
                    team_id=team_id,
                    moves=moves_by_round_team.get(round_number, {}).get(team_id, []),
                    characters_used=characters_by_round_team.get(round_number, {}).get(team_id, 0),
                )
            )


def _team_id_for_agent(agent_id: str, two_teams: bool) -> str:
    """Map an event's agent_id back to the team it belongs to."""
    if not two_teams:
        return TEAM_SOLO_ID
    return AGENT_ID_TO_TEAM_ID.get(agent_id, TEAM_SOLO_ID)


def _reconstruct_outcome(
    case: YardCase,
    round_number: int,
    team_id: str,
    moves: list[ContainerYardMoveJudged],
    characters_used: int,
) -> YardOutcome:
    """Build a ``YardOutcome`` for a completed round from grouped move verdicts."""
    budget_exceeded = characters_used >= case.round_time_budget_seconds
    placed_step_indices = {move.step_index for move in moves if move.accepted}
    first_terminal = next(
        (move for move in moves if not move.accepted and not move.soft_rejected), None
    )
    step_outcomes: list[StepOutcome] = []
    failure_step_index: int | None = None
    for step in case.steps:
        succeeded = step.step_index in placed_step_indices
        step_outcomes.append(
            StepOutcome(
                step_index=step.step_index,
                container_summary=render_container(container=step.container),
                intake_slot=step.intake_slot,
                target_slot=step.target_slot,
                succeeded=succeeded,
            )
        )
        if not succeeded and failure_step_index is None:
            failure_step_index = step.step_index
    steps_succeeded = sum(1 for outcome in step_outcomes if outcome.succeeded)
    round_succeeded = steps_succeeded == len(case.steps) and not budget_exceeded
    if round_succeeded:
        failure_reason = ""
    elif budget_exceeded:
        failure_reason = "Communication budget exhausted."
    elif first_terminal is not None:
        failure_reason = first_terminal.explanation
    else:
        failure_reason = "Round did not place every container."
    return YardOutcome(
        case_number=round_number,
        team_id=team_id,
        step_count=len(case.steps),
        steps_succeeded=steps_succeeded,
        step_outcomes=tuple(step_outcomes),
        budget_exceeded=budget_exceeded,
        characters_used=characters_used,
        round_time_budget_seconds=case.round_time_budget_seconds,
        round_succeeded=round_succeeded,
        failure_reason=failure_reason,
        failure_step_index=failure_step_index,
    )
