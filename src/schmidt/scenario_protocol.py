"""Abstract base class that every simulation scenario must implement.

Defines the contract for autonomous execution mode. Each scenario specifies
its agents, channels, injections, timing parameters, and evaluation logic.
"""

import argparse
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Self

from schmidt.evaluation.evaluation_report import EvaluationReport
from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool

logger = logging.getLogger(__name__)


class SimulationScenario(ABC):
    """Contract that a scenario plug-in must fulfil to run in autonomous mode.

    Each concrete subclass defines the agents, channels, prompt injections,
    timing parameters, and evaluation logic that comprise a single simulation
    scenario.
    """

    @classmethod
    def get_available_evaluator_names(cls) -> list[str]:
        """Return the names of all evaluators available for this scenario.

        The default returns only generic evaluators (mirroring
        ``GENERIC_EVALUATOR_REGISTRY`` — imported there from each evaluator's
        ``name`` class attribute, but listed here to avoid a circular import).
        Scenarios with scenario-specific evaluators override this method.
        """
        return [
            "communication_pattern",
            "cooperation",
            "instruction_adherence",
            "secret_leak",
        ]

    @classmethod
    @abstractmethod
    def add_cli_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """Register scenario-specific CLI arguments on the given parser."""
        ...

    @classmethod
    @abstractmethod
    def create(cls, args: argparse.Namespace) -> Self:
        """Parse scenario-specific CLI arguments and construct a scenario instance."""
        ...

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct a scenario from its serialized config dict.

        The ``config`` is the same dict returned by ``get_scenario_config()``,
        stored in the ``SimulationStarted`` event. Used by the fork API to
        reconstruct scenarios without CLI arguments.

        Subclasses that support forking must override this method.
        """
        raise NotImplementedError(
            f"{cls.__name__} does not implement create_from_config. "
            "Override this method to support simulation forking."
        )

    @abstractmethod
    def name(self) -> str:
        """Return the unique identifier for this scenario."""
        ...

    @abstractmethod
    def scenario_description(self) -> str:
        """Return a markdown description of what this scenario simulates."""
        ...

    @abstractmethod
    def get_agents(self, default_model: str) -> list[AgentConfig]:
        """Return the list of agent configurations participating in this scenario."""
        ...

    @abstractmethod
    def get_channels(self) -> list[Channel]:
        """Return the communication channels available in this scenario."""
        ...

    @abstractmethod
    def get_channel_display_name(self, channel_id: str, agent_id: str) -> str:
        """Return the display name of a channel as seen by a specific agent."""
        ...

    @abstractmethod
    def get_agent_display_name(self, agent_id: str) -> str:
        """Return the human-readable display name for an agent."""
        ...

    def get_scenario_config(self) -> dict[str, object]:
        """Return scenario configuration as a JSON-serializable dict for logging and display.

        Subclasses override this to expose their knobs. The default returns
        an empty dict, so scenarios without configuration need no changes.
        """
        return {}

    @abstractmethod
    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return an injected prompt message for an agent at a given round.

        Returns None when no injection is scheduled for this round and agent.
        """
        ...

    @abstractmethod
    async def run_evaluation(
        self,
        log_path: Path,
        evaluator_names: list[str],
        report_path: Path,
        model: str,
        provider_name: str,
        inference_provider: str | None,
        reasoning_effort: str | None,
    ) -> EvaluationReport:
        """Run evaluators against a simulation log and write the report."""
        ...

    # --- Autonomous agent timing configuration ---

    @abstractmethod
    def get_round_count(self) -> int:
        """Return the total number of rounds in this scenario."""
        ...

    @abstractmethod
    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last before force-advancing."""
        ...

    @abstractmethod
    def get_agent_reaction_delay_range(self, agent_id: str) -> tuple[float, float]:
        """Return the (min, max) seconds an agent waits before reacting to a notification."""
        ...

    @abstractmethod
    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return scenario-specific tools to register on the MCP server.

        Each tool is exposed alongside the base communication tools
        (check_messages, read_channel, send_message, etc.). Return an
        empty list if the scenario has no custom tools.
        """
        ...

    def set_run_dir(self, run_dir: Path) -> None:
        """Called after the run directory is computed but before the simulation starts.

        Scenarios that need filesystem access (e.g. code workspaces) override
        this to store the path and create subdirectories. The default is a no-op.
        """

    def is_finished_early(self) -> bool:
        """Return True if the scenario has reached a natural conclusion before max rounds.

        The game clock checks this each iteration and terminates the simulation
        early when it returns True. The default returns False.
        """
        return False

    def on_round_advanced(self, round_number: int) -> None:
        """Called by the game clock after advancing to a new round.

        Scenarios with mutable world state override this to resolve pending
        actions (effort allocations, status updates) and advance the simulation.
        The default is a no-op for scenarios without world state.
        """
