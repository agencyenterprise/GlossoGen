"""Shared helpers for Veyru round-success scoring.

Used by ``RoundSuccessMetric`` (scores every round in the log) and
``RoundSuccessAfterResumeMetric`` (scores only the rounds played
after a replace-agent swap). Centralising the team-result accounting
keeps the two metrics in lock-step on win/loss semantics.
"""

import logging
from typing import NamedTuple

from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import (
    MessageSent,
    RoundAdvanced,
    SimulationEvent,
    ToolResultReceived,
    WorldEventDelivered,
)
from schmidt.scenarios.veyru.ids import (
    NEW_SYMPTOMS_MARKER,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    STABILIZATION_ENGINEER_A_ID,
    STABILIZATION_ENGINEER_B_ID,
    STABILIZATION_SUCCESS_MARKER,
    STABILIZE_VEYRU_TOOL,
    VEYRU_COLLAPSED_MARKER,
)

logger = logging.getLogger(__name__)


TEAM_A_AGENT_IDS = frozenset({OBSERVER_A_ID, STABILIZATION_ENGINEER_A_ID})
TEAM_B_AGENT_IDS = frozenset({OBSERVER_B_ID, STABILIZATION_ENGINEER_B_ID})


class RoundOutcome(NamedTuple):
    """A single round's outcome for one team."""

    round_number: int
    won: bool
    note: str


class TeamResult(NamedTuple):
    """Accumulated per-team round outcomes."""

    won: int
    won_rounds: list[int]
    lost_details: list[str]
    round_outcomes: list[RoundOutcome]


def compute_team_result(
    round_numbers: list[int],
    events: list[SimulationEvent],
    label: str,
) -> TeamResult:
    """Tally stabilized, collapsed, and partial rounds for ``round_numbers``."""
    stabilized_rounds = _find_stabilized_rounds(events=events)
    collapsed_rounds = _find_collapsed_rounds(events=events)
    partial_rounds = _find_partial_rounds(events=events)

    won = 0
    won_rounds: list[int] = []
    lost_details: list[str] = []
    round_outcomes: list[RoundOutcome] = []
    for rnd in round_numbers:
        if rnd in stabilized_rounds:
            won += 1
            won_rounds.append(rnd)
            round_outcomes.append(RoundOutcome(round_number=rnd, won=True, note="stabilized"))
            continue
        if rnd in collapsed_rounds:
            if rnd in partial_rounds:
                detail = f"{label} R{rnd}: collapsed (partial stages)"
                note = "collapsed (partial stages)"
            else:
                detail = f"{label} R{rnd}: collapsed"
                note = "collapsed"
            lost_details.append(detail)
            round_outcomes.append(RoundOutcome(round_number=rnd, won=False, note=note))
            continue
        if rnd in partial_rounds:
            detail = f"{label} R{rnd}: partial stages, not fully stabilized"
            note = "partial stages, not fully stabilized"
        else:
            detail = f"{label} R{rnd}: no successful stabilization"
            note = "no successful stabilization"
        lost_details.append(detail)
        round_outcomes.append(RoundOutcome(round_number=rnd, won=False, note=note))
    return TeamResult(
        won=won,
        won_rounds=won_rounds,
        lost_details=lost_details,
        round_outcomes=round_outcomes,
    )


def is_two_team_mode(agent_configs: list[AgentConfig]) -> bool:
    """Detect two-team mode from the set of registered agent IDs."""
    agent_ids = {config.agent_id for config in agent_configs}
    return "observer_a" in agent_ids and "observer_b" in agent_ids


def filter_events_for_team(
    events: list[SimulationEvent],
    agent_ids: frozenset[str],
    link_channel_id: str,
) -> list[SimulationEvent]:
    """Return only the events attributable to a single team."""
    filtered: list[SimulationEvent] = []
    for event in events:
        if isinstance(event, ToolResultReceived):
            if event.agent_id in agent_ids:
                filtered.append(event)
            continue
        if isinstance(event, WorldEventDelivered):
            if event.agent_id in agent_ids:
                filtered.append(event)
            continue
        if isinstance(event, MessageSent):
            if event.message.channel_id == link_channel_id:
                filtered.append(event)
            continue
        if isinstance(event, RoundAdvanced):
            filtered.append(event)
    return filtered


def count_total_rounds(events: list[SimulationEvent]) -> int:
    """Return the highest round number observed in ``RoundAdvanced`` events."""
    max_round = 0
    for event in events:
        if isinstance(event, RoundAdvanced):
            if event.round_number > max_round:
                max_round = event.round_number
    return max_round


def collect_advanced_round_numbers(events: list[SimulationEvent]) -> set[int]:
    """Return every round number that actually advanced (had a ``RoundAdvanced`` event)."""
    return {event.round_number for event in events if isinstance(event, RoundAdvanced)}


def _find_stabilized_rounds(events: list[SimulationEvent]) -> set[int]:
    """Return the set of rounds fully stabilized (final stage completed)."""
    rounds: set[int] = set()
    for event in events:
        if not isinstance(event, ToolResultReceived):
            continue
        if event.tool_name != STABILIZE_VEYRU_TOOL:
            continue
        if STABILIZATION_SUCCESS_MARKER not in event.result:
            continue
        if NEW_SYMPTOMS_MARKER in event.result:
            continue
        rounds.add(event.round_number)
    return rounds


def _find_collapsed_rounds(events: list[SimulationEvent]) -> set[int]:
    """Return the set of rounds where the Veyru collapsed."""
    rounds: set[int] = set()
    for event in events:
        if not isinstance(event, WorldEventDelivered):
            continue
        if VEYRU_COLLAPSED_MARKER in event.text:
            rounds.add(event.round_number)
    return rounds


def _find_partial_rounds(events: list[SimulationEvent]) -> set[int]:
    """Return rounds where at least one intermediate stage was stabilized.

    Intermediate-stage tool results contain both ``STABILIZATION_SUCCESS_MARKER``
    and ``NEW_SYMPTOMS_MARKER``; the scenario emits that combined phrasing when a
    stage clears but more stages remain.
    """
    rounds: set[int] = set()
    for event in events:
        if not isinstance(event, ToolResultReceived):
            continue
        if event.tool_name != STABILIZE_VEYRU_TOOL:
            continue
        if STABILIZATION_SUCCESS_MARKER in event.result and NEW_SYMPTOMS_MARKER in event.result:
            rounds.add(event.round_number)
    return rounds
