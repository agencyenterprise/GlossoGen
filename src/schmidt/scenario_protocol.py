"""Abstract base class that every simulation scenario must implement."""

import argparse
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Self

from schmidt.evaluation.evaluation_report import EvaluationReport
from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel
from schmidt.models.shared_document_config import SharedDocumentConfig
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

    def get_shared_documents(self) -> list[SharedDocumentConfig]:
        """Return shared document definitions for this scenario.

        Shared documents are persistent artifacts visible to multiple agents.
        Each document specifies reader and writer access per agent. The hub
        registers ``list_documents``, ``read_document``, and ``write_document``
        tools when this returns a non-empty list.

        Defaults to an empty list. Override in subclasses that use shared docs.
        """
        return []

    @abstractmethod
    def get_checkpoint(self) -> dict[str, Any]:
        """Serialize the scenario's internal turn-scheduling and world state.

        Called at each turn boundary so the simulation can be resumed after an
        error. Stateful scenarios should include their world state alongside
        the turn-scheduling fields. The returned dict must be JSON-serializable.
        """
        ...

    @abstractmethod
    def restore_from_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Restore the scenario's internal state from a previously saved checkpoint.

        Called during resume before the turn loop restarts. The ``checkpoint``
        dict is the same structure returned by ``get_checkpoint()``.
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
        reasoning_effort: str | None,
    ) -> EvaluationReport:
        """Run evaluators against a simulation log and write the report."""
        ...
