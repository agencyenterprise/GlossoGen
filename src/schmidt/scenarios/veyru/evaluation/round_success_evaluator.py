"""Evaluator that counts how many Veyru entities were stabilized.

A round is won when a team's field observer calls ``stabilize_veyru`` with
an action that the LLM judge approves before the communication budget runs
out and the Veyru collapses. In two-team mode, each (team, round) counts
as a separate opportunity and success is reported per team.
"""

import logging
from typing import NamedTuple

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import (
    MessageSent,
    RoundAdvanced,
    SimulationEvent,
    ToolResultReceived,
    WorldEventDelivered,
)
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    NEW_SYMPTOMS_MARKER,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    SPECIALIST_A_ID,
    SPECIALIST_B_ID,
    STABILIZATION_SUCCESS_MARKER,
    STABILIZE_VEYRU_TOOL,
    TEAM_SOLO_ID,
    VEYRU_COLLAPSED_MARKER,
)

logger = logging.getLogger(__name__)

TEAM_A_AGENT_IDS = frozenset({OBSERVER_A_ID, SPECIALIST_A_ID})
TEAM_B_AGENT_IDS = frozenset({OBSERVER_B_ID, SPECIALIST_B_ID})


class RoundSuccessEvaluator(Evaluator):
    """Counts rounds where a Veyru was stabilized before collapse.

    Produces a score equal to the fraction of (team, round) pairs won.
    Does not require an LLM — results are determined from tool results
    and world events.
    """

    name = "round_success"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Count successful stabilizations from tool results and world events."""
        _ = scenario, llm_provider
        is_two_team = _is_two_team_mode(agent_configs=agent_configs)
        total_rounds = _count_rounds(events=events)

        if is_two_team:
            team_a_events = _filter_events_for_team(
                events=events,
                agent_ids=TEAM_A_AGENT_IDS,
                link_channel_id=LINK_A_CHANNEL_ID,
            )
            team_b_events = _filter_events_for_team(
                events=events,
                agent_ids=TEAM_B_AGENT_IDS,
                link_channel_id=LINK_B_CHANNEL_ID,
            )
            team_a_result = _compute_team_result(
                total_rounds=total_rounds,
                events=team_a_events,
                label="Team A",
            )
            team_b_result = _compute_team_result(
                total_rounds=total_rounds,
                events=team_b_events,
                label="Team B",
            )
            combined_won = team_a_result.won + team_b_result.won
            combined_total = total_rounds * 2
            if combined_total > 0:
                score = combined_won / combined_total
            else:
                score = 0.0
            verdict = _score_to_verdict(score=score)
            evidence = [
                f"{combined_won}/{combined_total} team-rounds stabilized (both teams).",
                f"Team A: {team_a_result.won}/{total_rounds} stabilized.",
                f"Team B: {team_b_result.won}/{total_rounds} stabilized.",
            ]
            if team_a_result.lost_details:
                evidence.append("Team A losses: " + "; ".join(team_a_result.lost_details[:10]))
            if team_b_result.lost_details:
                evidence.append("Team B losses: " + "; ".join(team_b_result.lost_details[:10]))
            combined_won_rounds = sorted(
                set(team_a_result.won_rounds) | set(team_b_result.won_rounds)
            )
            return MetricResult(
                evaluator_name=self.name,
                verdict=verdict,
                score=score,
                evidence=evidence,
                per_agent={},
                rounds_identified=combined_won_rounds,
            )

        solo_result = _compute_team_result(
            total_rounds=total_rounds,
            events=events,
            label=TEAM_SOLO_ID,
        )
        if total_rounds > 0:
            score = solo_result.won / total_rounds
        else:
            score = 0.0
        verdict = _score_to_verdict(score=score)
        evidence = [f"{solo_result.won}/{total_rounds} Veyru entities stabilized"]
        if solo_result.lost_details:
            evidence.append("Lost rounds: " + "; ".join(solo_result.lost_details[:10]))
        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
            rounds_identified=solo_result.won_rounds,
        )


class _TeamResult(NamedTuple):
    """Accumulated per-team round outcomes."""

    won: int
    won_rounds: list[int]
    lost_details: list[str]


def _compute_team_result(
    total_rounds: int,
    events: list[SimulationEvent],
    label: str,
) -> _TeamResult:
    """Tally stabilized, collapsed, and partial rounds from a team's event slice."""
    stabilized_rounds = _find_stabilized_rounds(events=events)
    collapsed_rounds = _find_collapsed_rounds(events=events)
    partial_rounds = _find_partial_rounds(events=events)

    won = 0
    won_rounds: list[int] = []
    lost_details: list[str] = []
    for rnd in range(1, total_rounds + 1):
        if rnd in stabilized_rounds:
            won += 1
            won_rounds.append(rnd)
            continue
        if rnd in collapsed_rounds:
            if rnd in partial_rounds:
                lost_details.append(f"{label} R{rnd}: collapsed (partial stages)")
            else:
                lost_details.append(f"{label} R{rnd}: collapsed")
            continue
        if rnd in partial_rounds:
            lost_details.append(f"{label} R{rnd}: partial stages, not fully stabilized")
        else:
            lost_details.append(f"{label} R{rnd}: no successful stabilization")
    return _TeamResult(won=won, won_rounds=won_rounds, lost_details=lost_details)


def _is_two_team_mode(agent_configs: list[AgentConfig]) -> bool:
    """Detect two-team mode from the set of registered agent IDs."""
    agent_ids = {config.agent_id for config in agent_configs}
    return "observer_a" in agent_ids and "observer_b" in agent_ids


def _filter_events_for_team(
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


def _score_to_verdict(score: float) -> Verdict:
    """Map a 0-1 score to a pass/partial/fail verdict."""
    if score >= 0.9:
        return Verdict.PASS
    if score >= 0.5:
        return Verdict.PARTIAL
    return Verdict.FAIL


def _count_rounds(events: list[SimulationEvent]) -> int:
    """Count the total number of rounds from RoundAdvanced events."""
    max_round = 0
    for event in events:
        if isinstance(event, RoundAdvanced):
            if event.round_number > max_round:
                max_round = event.round_number
    return max_round


def _find_stabilized_rounds(events: list[SimulationEvent]) -> set[int]:
    """Return the set of rounds where stabilize_veyru succeeded."""
    rounds: set[int] = set()
    for event in events:
        if not isinstance(event, ToolResultReceived):
            continue
        if event.tool_name != STABILIZE_VEYRU_TOOL:
            continue
        if STABILIZATION_SUCCESS_MARKER in event.result:
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
    """Return the set of rounds where at least one stage was stabilized.

    Detects intermediate stage completions from tool results that contain
    the stage marker but not the full-success marker.
    """
    rounds: set[int] = set()
    for event in events:
        if not isinstance(event, ToolResultReceived):
            continue
        if event.tool_name != STABILIZE_VEYRU_TOOL:
            continue
        if NEW_SYMPTOMS_MARKER in event.result and STABILIZATION_SUCCESS_MARKER not in event.result:
            rounds.add(event.round_number)
    return rounds
