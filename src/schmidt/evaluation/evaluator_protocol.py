"""Abstract base class and factory type alias for simulation evaluators."""

from abc import ABC, abstractmethod
from collections.abc import Callable

from schmidt.evaluation.evaluation_report import MetricResult
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario


class Evaluator(ABC):
    """Base class for simulation evaluators.

    Subclasses implement the ``evaluate`` method to score a completed
    simulation run and return a single ``MetricResult``.
    Each evaluator must declare a unique ``name`` class attribute used
    for registry lookup and reporting.
    """

    name: str
    """Unique identifier for this evaluator, used in registries and reports."""

    @abstractmethod
    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
    ) -> MetricResult:
        """Score a simulation run and produce a metric result.

        Args:
            events: The full ordered list of events recorded during the simulation.
            agent_configs: Configuration objects for each agent that participated.
            scenario: The scenario definition that was used for the simulation.
            llm_provider: An LLM provider available for evaluators that need to
                call a language model as part of their scoring logic.

        Returns:
            A ``MetricResult`` containing the computed score and associated metadata.
        """
        ...


EvaluatorFactory = Callable[[], Evaluator]
"""A zero-argument callable that produces an ``Evaluator`` instance."""
