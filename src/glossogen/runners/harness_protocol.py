"""The contract a harness implements to drive seats in a simulation.

A harness builds the ``AgentRunner`` for a seat and answers two questions the
platform asks before a run starts: what the environment is missing for the seats
it will drive, and whether it can hold a model response until the scenario
releases it. Everything a runner does while the run is live goes through the
``AgentRunner`` it builds.

A harness in another distribution declares itself under the
``glossogen.agent_harnesses.v<N>`` entry-point group; see
:mod:`glossogen.runners.harness_loader`.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import NamedTuple

from glossogen.event_bus import EventBus
from glossogen.model_catalog import Provider
from glossogen.runners.agent_runner_base import AgentRunner


class RunnerBuildContext(NamedTuple):
    """What every runner is built with, whichever harness builds it.

    ``run_dir`` is the run's directory, where a harness that keeps per-seat
    state on disk puts it.
    """

    max_turns: int
    event_bus: EventBus
    run_id: str
    scenario_name: str
    telemetry_enabled: bool
    run_dir: Path


class HarnessSeat(NamedTuple):
    """One seat a harness will drive, as named in a launch check's message."""

    name: str
    model: str
    provider: Provider


class AgentHarness(ABC):
    """Builds runners for the seats that name it, and checks it can before the run starts."""

    @classmethod
    @abstractmethod
    def name(cls) -> str:
        """The name a seat records and a launch selects this harness by."""

    @classmethod
    @abstractmethod
    def gates_model_responses(cls) -> bool:
        """Whether runners from this harness hold a response in ``gate_model_response``.

        The pydantic-ai runner awaits the scenario's gate before any of a
        response's tool calls run. A harness that only learns of a response once
        its tools are already executing answers False, and a scenario that needs
        the hold refuses such a seat at launch.
        """

    @classmethod
    @abstractmethod
    def preflight(cls, seats: tuple[HarnessSeat, ...]) -> tuple[str, ...]:
        """What stands between this harness and driving ``seats``, as things to go and do.

        Provider credentials are checked by the platform for every seat; this
        covers what only the harness knows, such as an optional dependency or a
        binary it needs. Empty means the harness is ready.
        """

    @classmethod
    @abstractmethod
    def build_runner(cls, context: RunnerBuildContext) -> AgentRunner:
        """A runner for one seat."""
