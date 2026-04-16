"""Evaluator that counts how many rounds the team won in a telephone simulation.

A round is won when the Receiver submits all items correctly and the
Relayer stays within the character budget.
"""

import logging
import re

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import RoundAdvanced, SimulationEvent, ToolResultReceived
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

SUBMIT_ANSWER_TOOL = "submit_answer"
ACCURACY_PATTERN = re.compile(r"(\d+)/(\d+) items correct \((\d+)%\)")
BUDGET_EXCEEDED_MARKER = "ROUND LOST"


class RoundSuccessEvaluator(Evaluator):
    """Counts rounds won: 100% accuracy and budget not exceeded.

    Produces a label like ``eval:round_success:25/40`` and a score
    equal to the fraction of rounds won.
    """

    name = "round_success"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Count successful rounds from submit_answer tool results."""
        _ = agent_configs, scenario, llm_provider

        total_rounds = self._count_rounds(events=events)
        results_by_round = self._extract_round_results(events=events)

        won = 0
        lost_rounds: list[str] = []
        for rnd in sorted(results_by_round.keys()):
            result_text = results_by_round[rnd]
            match = ACCURACY_PATTERN.search(result_text)
            if match is None:
                lost_rounds.append(f"R{rnd}: no parseable result")
                continue

            correct = int(match.group(1))
            total = int(match.group(2))
            budget_exceeded = BUDGET_EXCEEDED_MARKER in result_text

            if correct == total and not budget_exceeded:
                won += 1
            else:
                reason = []
                if correct < total:
                    reason.append(f"{correct}/{total} correct")
                if budget_exceeded:
                    reason.append("budget exceeded")
                lost_rounds.append(f"R{rnd}: {', '.join(reason)}")

        no_submission_count = total_rounds - len(results_by_round)

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

        evidence = [f"{won}/{total_rounds} rounds won"]
        if no_submission_count > 0:
            evidence.append(f"{no_submission_count} rounds had no answer submitted")
        if lost_rounds:
            evidence.append("Lost rounds: " + "; ".join(lost_rounds[:10]))

        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
        )

    def _count_rounds(self, events: list[SimulationEvent]) -> int:
        """Count the total number of rounds from RoundAdvanced events."""
        max_round = 0
        for event in events:
            if isinstance(event, RoundAdvanced):
                if event.round_number > max_round:
                    max_round = event.round_number
        return max_round

    def _extract_round_results(self, events: list[SimulationEvent]) -> dict[int, str]:
        """Extract the submit_answer result text per round."""
        results: dict[int, str] = {}
        for event in events:
            if not isinstance(event, ToolResultReceived):
                continue
            if event.tool_name != SUBMIT_ANSWER_TOOL:
                continue
            results[event.round_number] = event.result
        return results
