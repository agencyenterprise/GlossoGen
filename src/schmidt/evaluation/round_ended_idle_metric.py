"""Metric that flags rounds whose main phase ended via ``all_agents_idle``.

Scenario-agnostic: reads ``RoundEnded`` events emitted by the generic game
clock. A round is flagged when its main phase terminated because every
agent was blocked on ``read_notifications``.
"""

import logging
from pathlib import Path

from schmidt.evaluation.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
from schmidt.evaluation.round_end_trigger_detection import count_rounds, find_round_end_triggers
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

_IDLE_TRIGGER = "all_agents_idle"


class RoundEndedIdleMetric(Metric):
    """Counts rounds whose main phase ended because all agents went idle."""

    name = "round_ended_idle"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> list[Measurement]:
        """Identify rounds that ended via the idle trigger."""
        _ = agent_configs, scenario, llm_provider, run_dir
        total_rounds = count_rounds(events=events)
        triggers = find_round_end_triggers(events=events)

        if total_rounds > 0 and not triggers:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="rounds ended via all_agents_idle",
                    summary=(
                        "round_ended_idle metric requires round_ended events; "
                        "this run predates that event type — re-run the scenario to re-evaluate."
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]

        identified = sorted(r for r, trigger in triggers.items() if trigger == _IDLE_TRIGGER)
        per_round = [
            RoundObservation(round_number=r, value=1.0, note=_IDLE_TRIGGER) for r in identified
        ]
        summary = (
            f"{len(identified)}/{total_rounds} rounds ended with the all_agents_idle "
            f"trigger: {identified}"
        )

        logger.info(
            "round_ended_idle: total=%d identified=%s",
            total_rounds,
            identified,
        )
        return [
            Measurement(
                metric_name=self.name,
                score=float(len(identified)),
                score_unit=f"rounds ended via all_agents_idle (out of {total_rounds})",
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]
