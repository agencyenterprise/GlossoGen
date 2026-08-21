"""The contract every metric implements.

``compute`` is the only entry point for scoring. It receives the run's events, the
agent configs, the scenario and an LLM provider, and returns a list of measurements.

The empty-list convention is the part worth knowing before writing one, and
``compute`` documents it in full.

``read_keyed_observations`` is the second, optional half: a metric that wrote numbers
to a file beside its report tells the analysis layer how to read them back. Metrics
that write no such file inherit the default and return nothing.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from glossogen.evaluation.metric_core.keyed_observation import KeyedObservation
from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario


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
            an empty list, so the report records no entry for that metric,
            which is cleaner than a zero-score sentinel with a
            "does not apply" summary.
        """
        ...

    async def read_keyed_observations(self, run_dir: Path) -> list[KeyedObservation]:
        """Return numbers this metric wrote beside the report, keyed by their own axis.

        Implement this when ``compute`` writes a sidecar file holding per-category,
        per-question, or per-message numbers that do not fit ``per_round`` or
        ``per_agent``. The analysis layer calls it to make those numbers groupable,
        and it is the only way they reach a chart: a ``Measurement`` has nowhere to
        put them.

        A run whose sidecar is absent or unreadable yields an empty list rather than
        an error. Sweeping a few thousand runs will meet a file written by an older
        version of the metric, and one such file must not fail the whole selection.

        Args:
            run_dir: On-disk directory holding the run's log, report, and sidecars.

        Returns:
            One :class:`KeyedObservation` per number, or an empty list. The default
            implementation returns an empty list, which is correct for every metric
            that writes no sidecar.
        """
        del run_dir
        return []
