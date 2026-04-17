"""Evaluator that counts how many Veyru entities were stabilized.

A round is won when the field observer calls ``stabilize_veyru`` with an
action that the LLM judge approves before the communication budget runs
out and the Veyru collapses.
"""

import logging

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import (
    RoundAdvanced,
    SimulationEvent,
    ToolResultReceived,
    WorldEventDelivered,
)
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

STABILIZE_TOOL = "stabilize_veyru"
SUCCESS_MARKER = "Stabilization successful"
COLLAPSED_MARKER = "VEYRU HAS COLLAPSED"


class RoundSuccessEvaluator(Evaluator):
    """Counts rounds where the Veyru was stabilized before collapse.

    Produces a score equal to the fraction of rounds won. Does not
    require an LLM — results are determined from tool results and
    world events.
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
        _ = agent_configs, scenario, llm_provider

        total_rounds = _count_rounds(events=events)
        stabilized_rounds = _find_stabilized_rounds(events=events)
        collapsed_rounds = _find_collapsed_rounds(events=events)

        won = 0
        lost_details: list[str] = []
        for rnd in range(1, total_rounds + 1):
            if rnd in stabilized_rounds:
                won += 1
            elif rnd in collapsed_rounds:
                lost_details.append(f"R{rnd}: collapsed")
            else:
                lost_details.append(f"R{rnd}: no successful stabilization")

        if total_rounds > 0:
            score = won / total_rounds
        else:
            score = 0.0

        if score >= 0.9:
            verdict = Verdict.PASS
        elif score >= 0.5:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.FAIL

        evidence = [f"{won}/{total_rounds} Veyru entities stabilized"]
        if lost_details:
            evidence.append("Lost rounds: " + "; ".join(lost_details[:10]))

        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
        )


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
        if event.tool_name != STABILIZE_TOOL:
            continue
        if SUCCESS_MARKER in event.result:
            rounds.add(event.round_number)
    return rounds


def _find_collapsed_rounds(events: list[SimulationEvent]) -> set[int]:
    """Return the set of rounds where the Veyru collapsed."""
    rounds: set[int] = set()
    for event in events:
        if not isinstance(event, WorldEventDelivered):
            continue
        if COLLAPSED_MARKER in event.text:
            rounds.add(event.round_number)
    return rounds
