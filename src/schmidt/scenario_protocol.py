"""Abstract base class that every simulation scenario must implement."""

import argparse
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Self

from schmidt.evaluation.evaluation_report import EvaluationReport
from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel
from schmidt.models.simulation_state import SimulationState, TurnDecision
from schmidt.tools.tool_registry import ToolRegistry


class SimulationScenario(ABC):
    """Contract that a scenario plug-in must fulfil to be run by the simulation hub.

    Each concrete subclass defines the agents, channels, turn logic, prompt
    injections, and tools that comprise a single simulation scenario.
    """

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

    @abstractmethod
    def name(self) -> str:
        """Return the unique identifier for this scenario."""
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

    @abstractmethod
    async def decide_next_turn(self, state: SimulationState) -> TurnDecision | None:
        """Determine which agent acts next given the current simulation state.

        Returns None when the simulation should end.
        """
        ...

    @abstractmethod
    def get_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return an injected prompt message for an agent at a given round.

        Returns None when no injection is scheduled for this round and agent.
        """
        ...

    @abstractmethod
    def register_tools(self, registry: ToolRegistry) -> None:
        """Register scenario-specific tools with the provided tool registry."""
        ...

    @abstractmethod
    async def run_evaluation(
        self,
        log_path: Path,
        evaluator_names: list[str],
        report_path: Path,
        model: str,
    ) -> EvaluationReport:
        """Run evaluators against a simulation log and write the report."""
        ...
