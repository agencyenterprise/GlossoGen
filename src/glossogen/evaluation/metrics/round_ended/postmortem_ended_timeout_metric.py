"""Metric that flags rounds whose postmortem phase ended via ``postmortem_timeout``.

Scenario-agnostic. The postmortem-phase counterpart of ``round_ended_timeout``.
A round is flagged when its postmortem discussion phase terminated because the
wall-clock duration limit was reached, rather than because all agents went idle.

Reads ``PostmortemEnded`` events (authoritative; includes the final round) with a
fallback to ``RoundAdvanced(trigger='postmortem_timeout')`` for runs that predate
the ``PostmortemEnded`` event, so it scores existing runs without re-execution.
"""

import logging
from pathlib import Path

from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metrics.round_ended.trigger_detection import (
    count_postmortem_phases,
    find_postmortem_timeout_rounds,
)
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

_TIMEOUT_TRIGGER = "postmortem_timeout"


class PostmortemEndedTimeoutMetric(Metric):
    """Counts rounds whose postmortem phase ended because the wall-clock timeout was reached."""

    name = "postmortem_ended_timeout"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Identify rounds whose postmortem phase ended via the wall-clock timeout trigger."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        postmortem_phases = count_postmortem_phases(events=events)
        if postmortem_phases == 0:
            logger.info("postmortem_ended_timeout: no postmortem phases in run; skipping")
            return []

        identified = sorted(find_postmortem_timeout_rounds(events=events))
        per_round = [
            RoundObservation(round_number=r, value=1.0, note=_TIMEOUT_TRIGGER) for r in identified
        ]
        summary = (
            f"{len(identified)}/{postmortem_phases} postmortem phases ended with the "
            f"postmortem_timeout trigger: {identified}"
        )

        logger.info(
            "postmortem_ended_timeout: postmortem_phases=%d identified=%s",
            postmortem_phases,
            identified,
        )
        return [
            Measurement(
                metric_name=self.name,
                score=float(len(identified)),
                score_unit=f"postmortem phases ended via timeout (out of {postmortem_phases})",
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]
