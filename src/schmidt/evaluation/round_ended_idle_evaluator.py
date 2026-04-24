"""Evaluator that flags rounds whose main phase ended via ``all_agents_idle``.

Scenario-agnostic: reads ``RoundEnded`` events emitted by the generic game
clock. A round is flagged when its main phase terminated because every
agent was blocked on ``read_notifications``.
"""

import logging
from pathlib import Path

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.evaluation.round_end_trigger_detection import count_rounds, find_round_end_triggers
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

_IDLE_TRIGGER = "all_agents_idle"


class RoundEndedIdleEvaluator(Evaluator):
    """Flags rounds whose main phase ended because all agents went idle on
    ``read_notifications``.
    """

    name = "round_ended_idle"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> MetricResult:
        """Identify rounds that ended via the idle trigger."""
        _ = agent_configs, scenario, llm_provider, run_dir
        total_rounds = count_rounds(events=events)
        triggers = find_round_end_triggers(events=events)

        if total_rounds > 0 and not triggers:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.FAIL,
                score=0.0,
                evidence=[
                    "round_ended_idle evaluator requires round_ended events; "
                    "this run predates that event type — re-run the scenario to re-evaluate.",
                ],
                per_agent={},
                rounds_identified=[],
            )

        identified = sorted(r for r, trigger in triggers.items() if trigger == _IDLE_TRIGGER)
        if total_rounds > 0:
            score = len(identified) / total_rounds
        else:
            score = 0.0
        if identified:
            verdict = Verdict.PASS
        else:
            verdict = Verdict.FAIL
        evidence = [
            f"{len(identified)}/{total_rounds} rounds ended with the all_agents_idle "
            f"trigger: {identified}",
        ]
        logger.info(
            "round_ended_idle: total=%d identified=%s score=%.3f verdict=%s",
            total_rounds,
            identified,
            score,
            verdict.value,
        )
        return MetricResult(
            evaluator_name=self.name,
            verdict=verdict,
            score=score,
            evidence=evidence,
            per_agent={},
            rounds_identified=identified,
        )
