"""Metrics standing in for ones shipped by another distribution.

``ExternalWordCountMetric`` is a complete, working metric: it counts words on the
primary channel, which is enough to prove an externally-contributed metric runs
and writes a Measurement. The other two are the ways a declaration can be wrong.
"""

from pathlib import Path

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import MessageSent, SimulationEvent
from glossogen.scenario_protocol import SimulationScenario


class ExternalWordCountMetric(Metric):
    """Mean words per message on the scenario's primary channels."""

    name = "external_word_count"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Count words per message, or return nothing when there are no messages."""
        _ = agent_configs, llm_provider, run_dir, options
        channel_ids = {channel.channel_id for channel in scenario.get_primary_channels()}
        counts = [
            len(event.message.text.split())
            for event in events
            if isinstance(event, MessageSent) and event.message.channel_id in channel_ids
        ]
        if not counts:
            return []
        mean = sum(counts) / len(counts)
        return [
            Measurement(
                metric_name=self.name,
                score=mean,
                score_unit="words/message",
                summary=f"{mean:.2f} words per message across {len(counts)} messages",
                per_round=[],
                per_agent=[],
            )
        ]


class MisnamedMetric(Metric):
    """Declares one name and answers to another, which the registry refuses."""

    name = "not_the_declared_name"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Never called: the registry refuses this class before instantiating it."""
        _ = events, agent_configs, scenario, llm_provider, run_dir, options
        return []


NOT_A_METRIC = "a string, which is not a Metric subclass"
"""What an entry point pointing at the wrong object resolves to."""
