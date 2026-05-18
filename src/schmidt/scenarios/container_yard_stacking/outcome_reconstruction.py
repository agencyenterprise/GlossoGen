"""Rebuild per-team ``YardOutcome`` entries from a JSONL event list.

Used on resume / fork / replace-agent to seed the world's outcome history
so the next-round injection can render an accurate "previous round" block.
The reconstructor walks ``ContainerYardTruckJudged`` and
``ContainerYardCraneMoveJudged`` events to count successful trucks and
accepted moves per step, ``MessageSent`` events on the link channels to
recover each team's character usage, and ``RoundEnded`` events to know
which rounds are complete.
"""

from typing import Any

from schmidt.models.event import MessageSent, RoundEnded
from schmidt.scenarios.container_yard_stacking.events import (
    ContainerYardCraneMoveJudged,
    ContainerYardTruckJudged,
)
from schmidt.scenarios.container_yard_stacking.ids import TEAM_SOLO_ID
from schmidt.scenarios.container_yard_stacking.team_routing import (
    AGENT_ID_TO_TEAM_ID,
    team_id_for_channel,
)
from schmidt.scenarios.container_yard_stacking.world_state import (
    StepOutcome,
    TeamState,
    YardOutcome,
    stack_position_text,
)
from schmidt.scenarios.container_yard_stacking.yard_cases import YardCase


def restore_outcomes_from_events(
    teams: dict[str, TeamState],
    cases: list[YardCase],
    two_teams: bool,
    events: list[Any],
) -> None:
    """Append a ``YardOutcome`` to each team for every completed round in ``events``.

    Walks the per-round truck and crane verdict events, sums each
    team's link-channel message lengths to derive ``characters_used``
    and ``budget_exceeded``, and appends one ``YardOutcome`` per
    team per round whose ``RoundEnded`` event was logged.
    """
    trucks_by_round_step_team: dict[int, dict[str, dict[int, list[ContainerYardTruckJudged]]]] = {}
    cranes_by_round_step_team: dict[
        int, dict[str, dict[int, list[ContainerYardCraneMoveJudged]]]
    ] = {}
    characters_by_round_team: dict[int, dict[str, int]] = {}
    completed_rounds: set[int] = set()
    for event in events:
        round_number = getattr(event, "round_number", None)
        if not isinstance(round_number, int) or round_number < 1:
            continue
        if isinstance(event, ContainerYardTruckJudged):
            truck_team_id = _team_id_for_agent(agent_id=event.agent_id, two_teams=two_teams)
            truck_step_buckets = trucks_by_round_step_team.setdefault(round_number, {}).setdefault(
                truck_team_id, {}
            )
            truck_step_buckets.setdefault(event.step_index, []).append(event)
        elif isinstance(event, ContainerYardCraneMoveJudged):
            crane_team_id = _team_id_for_agent(agent_id=event.agent_id, two_teams=two_teams)
            crane_step_buckets = cranes_by_round_step_team.setdefault(round_number, {}).setdefault(
                crane_team_id, {}
            )
            crane_step_buckets.setdefault(event.step_index, []).append(event)
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
            if any(o.case_number == round_number for o in team.outcomes):
                continue
            team.outcomes.append(
                _reconstruct_outcome(
                    case=cases[round_number - 1],
                    round_number=round_number,
                    team_id=team_id,
                    trucks_by_step=trucks_by_round_step_team.get(round_number, {}).get(team_id, {}),
                    cranes_by_step=cranes_by_round_step_team.get(round_number, {}).get(team_id, {}),
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
    trucks_by_step: dict[int, list[ContainerYardTruckJudged]],
    cranes_by_step: dict[int, list[ContainerYardCraneMoveJudged]],
    characters_used: int,
) -> YardOutcome:
    """Build a ``YardOutcome`` for a completed round from grouped events."""
    budget_exceeded = characters_used >= case.round_time_budget_seconds
    step_outcomes: list[StepOutcome] = []
    failure_step_index: int | None = None
    first_failure_explanation = ""
    for step in case.steps:
        trucks_for_step = trucks_by_step.get(step.step_index, [])
        cranes_for_step = cranes_by_step.get(step.step_index, [])
        committed_count = sum(1 for t in trucks_for_step if t.overall_success)
        accepted_move_count = sum(1 for c in cranes_for_step if c.accepted)
        expected_truck_count = len(step.truck_assignments)
        expected_move_count = len(step.expected_move_sequence)
        succeeded = (
            committed_count == expected_truck_count and accepted_move_count == expected_move_count
        )
        step_outcomes.append(
            StepOutcome(
                step_index=step.step_index,
                incoming_container_id=step.incoming_container_id,
                target_position_text=stack_position_text(
                    stack=step.target_position.stack,
                    tier=step.target_position.tier,
                ),
                succeeded=succeeded,
                expected_move_count=expected_move_count,
                accepted_move_count=accepted_move_count,
                expected_truck_count=expected_truck_count,
                correctly_committed_truck_count=committed_count,
            )
        )
        if not succeeded and failure_step_index is None:
            failure_step_index = step.step_index
            first_failure_explanation = _first_failure_explanation(
                trucks_for_step=trucks_for_step,
                cranes_for_step=cranes_for_step,
            )
    steps_succeeded = sum(1 for s in step_outcomes if s.succeeded)
    round_succeeded = steps_succeeded == len(case.steps) and not budget_exceeded
    if round_succeeded:
        failure_reason = ""
    elif budget_exceeded:
        failure_reason = "Communication budget exhausted."
    elif first_failure_explanation != "":
        failure_reason = first_failure_explanation
    else:
        failure_reason = "Round did not complete every delivery."
    return YardOutcome(
        case_number=round_number,
        team_id=team_id,
        step_count=len(case.steps),
        steps_succeeded=steps_succeeded,
        step_outcomes=tuple(step_outcomes),
        total_expected_move_count=sum(s.expected_move_count for s in step_outcomes),
        total_accepted_move_count=sum(s.accepted_move_count for s in step_outcomes),
        total_expected_truck_count=sum(s.expected_truck_count for s in step_outcomes),
        total_correctly_committed_truck_count=sum(
            s.correctly_committed_truck_count for s in step_outcomes
        ),
        budget_exceeded=budget_exceeded,
        characters_used=characters_used,
        round_time_budget_seconds=case.round_time_budget_seconds,
        round_succeeded=round_succeeded,
        failure_reason=failure_reason,
        failure_step_index=failure_step_index,
    )


def _first_failure_explanation(
    trucks_for_step: list[ContainerYardTruckJudged],
    cranes_for_step: list[ContainerYardCraneMoveJudged],
) -> str:
    """Return the explanation string of the first failed truck or crane verdict for a step."""
    for truck in trucks_for_step:
        if not truck.overall_success:
            return truck.explanation
    for crane in cranes_for_step:
        if not crane.accepted:
            return crane.explanation
    return ""
