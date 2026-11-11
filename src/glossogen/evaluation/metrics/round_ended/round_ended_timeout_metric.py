"""Metric that flags rounds whose main phase ended via ``round_timeout``.

Scenario-agnostic: reads ``RoundEnded`` events emitted by the generic game
clock. A round is flagged when its main phase terminated because the
wall-clock duration limit was reached.
"""

from pathlib import Path

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metrics.round_ended.main_phase_ending_count import (
    count_main_phase_endings,
)
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.runtime.round_end_trigger import RoundEndTrigger
from glossogen.scenario_contract.scenario_base import ScenarioBase


class RoundEndedTimeoutMetric(Metric):
    """Counts rounds whose main phase ended because the wall-clock timeout was reached."""

    name = "round_ended_timeout"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Identify rounds that ended via the timeout trigger."""
        _ = agent_configs, scenario, llm_provider, run_dir, options
        return count_main_phase_endings(
            metric_name=self.name,
            trigger=RoundEndTrigger.ROUND_TIMEOUT,
            events=events,
        )
