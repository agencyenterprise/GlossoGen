"""Abstract base class and factory type alias for simulation metrics."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from schmidt.evaluation.measurement import Measurement
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

        Returns:
            A non-empty list of ``Measurement`` instances. Metrics that
            return a single number return a one-element list.
        """
        ...


MetricFactory = Callable[[], Metric]
"""A zero-argument callable that produces a ``Metric`` instance."""
