"""Abstract base class that every simulation scenario must implement.

Defines the unified contract for both autonomous and orchestrated execution
modes. Shared methods (agents, channels, injections, evaluation) are abstract.
Mode-specific methods have default implementations that raise
``NotImplementedError`` so scenarios only need to implement the methods
relevant to their supported mode(s).
"""

import argparse
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Self

from schmidt.evaluation.evaluation_report import EvaluationReport
from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel
from schmidt.models.shared_document_config import SharedDocumentConfig
from schmidt.models.simulation_state import SimulationState, TurnDecision
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool
from schmidt.tools.tool_registry import ToolRegistry


class SimulationScenario(ABC):
    """Contract that a scenario plug-in must fulfil to run in autonomous or orchestrated mode.

    Each concrete subclass defines the agents, channels, prompt injections,
    and evaluation logic that comprise a single simulation scenario. Depending
    on the execution mode, the subclass implements autonomous timing methods
    or orchestrated turn-scheduling methods (or both).
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
    # Scenarios that support autonomous mode override these. The default
    # implementations raise NotImplementedError for scenarios that only
    # support orchestrated mode.

    def get_round_count(self) -> int:
        """Return the total number of rounds in this scenario."""
        raise NotImplementedError("get_round_count is only available in autonomous mode scenarios")

    def get_max_round_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a round may last before force-advancing."""
        raise NotImplementedError(
            "get_max_round_duration_seconds is only available in autonomous mode scenarios"
        )

    def get_agent_reaction_delay_range(self, agent_id: str) -> tuple[float, float]:
        """Return the (min, max) seconds an agent waits before reacting to a notification."""
        raise NotImplementedError(
            "get_agent_reaction_delay_range is only available in autonomous mode scenarios"
        )

    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return scenario-specific tools to register on the MCP server.

        Each tool is exposed alongside the base communication tools
        (check_messages, read_channel, send_message, etc.). Return an
        empty list if the scenario has no custom tools.
        """
        raise NotImplementedError("get_mcp_tools is only available in autonomous mode scenarios")

    # --- Orchestrated turn-scheduling methods ---
    # Scenarios that support orchestrated mode override these. The default
    # implementations raise NotImplementedError for scenarios that only
    # support autonomous mode.

    async def decide_next_turn(self, state: SimulationState) -> TurnDecision | None:
        """Determine which agent acts next given the current simulation state.

        Returns None when the simulation should end.
        """
        raise NotImplementedError(
            "decide_next_turn is only available in orchestrated mode scenarios"
        )

    def register_tools(self, registry: ToolRegistry) -> None:
        """Register scenario-specific tools with the provided tool registry."""
        raise NotImplementedError("register_tools is only available in orchestrated mode scenarios")

    def get_checkpoint(self) -> dict[str, Any]:
        """Serialize the scenario's internal turn-scheduling and world state.

        Called at each turn boundary so the simulation can be resumed after an
        error. Stateful scenarios should include their world state alongside
        the turn-scheduling fields. The returned dict must be JSON-serializable.
        """
        raise NotImplementedError("get_checkpoint is only available in orchestrated mode scenarios")

    def restore_from_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Restore the scenario's internal state from a previously saved checkpoint.

        Called during resume before the turn loop restarts. The ``checkpoint``
        dict is the same structure returned by ``get_checkpoint()``.
        """
        raise NotImplementedError(
            "restore_from_checkpoint is only available in orchestrated mode scenarios"
        )
