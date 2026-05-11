"""Abstract base class for simulation metrics."""

from abc import ABC, abstractmethod
from pathlib import Path

from schmidt.evaluation.metric_core.measurement import Measurement
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario


class Metric(ABC):
    """Base class for simulation metrics.

    Subclasses implement ``compute`` to score a completed simulation run
    and return one or more ``Measurement`` instances. Most metrics return
    a single-element list; a metric that splits its output by team or
    other partition (e.g. veyru's two-team round_success) returns one
    Measurement per partition.
    """

    name: str
    """Unique identifier for this metric, used in registries and reports."""

    @abstractmethod
    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score a simulation run and produce one or more Measurements.

        Args:
            events: Full ordered list of events recorded during the simulation.
            agent_configs: Configuration objects for each agent that participated.
            scenario: The scenario definition used for the simulation.
            llm_provider: An LLM provider available for metrics that need to
                call a language model. Deterministic metrics ignore this.
            run_dir: On-disk directory holding the run's JSONL log, debug log,
                and any scenario outputs.
            options: Per-invocation options forwarded from the CLI. Most
                metrics ignore this; ``protocol_probe`` reads
                ``probe_round`` and ``probe_replicas`` from it.

        Returns:
            A list of ``Measurement`` instances. Most metrics return a
            one-element list; metrics that split their output by team or
            other partition return one Measurement per partition. A
            metric that detects it does not apply to this run (e.g.
            ``round_success_after_resume`` on a non-resume run,
            cross-team probe similarity on a single-team run) returns
            an empty list — the report records no entry for that metric,
            which is cleaner than a zero-score sentinel with a
            "does not apply" summary.
        """
        ...
