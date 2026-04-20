"""Abstract base class that every simulation scenario must implement.

Defines the contract for autonomous execution mode. Each scenario specifies
its agents, channels, injections, timing parameters, and evaluation logic.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Self

from schmidt.evaluation.evaluation_report import EvaluationReport
from schmidt.evaluation.generic_evaluator_names import GENERIC_EVALUATOR_NAMES
from schmidt.models.agent_config import AgentConfig, AgentRole
from schmidt.models.channel import Channel
from schmidt.runtime.scenario_mcp_tool import ScenarioMcpTool
from schmidt.runtime.scenario_world import ScenarioWorld

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

        The default returns only generic evaluators.
        Scenarios with scenario-specific evaluators override this method.
        """
        return sorted(GENERIC_EVALUATOR_NAMES)

    @classmethod
    @abstractmethod
    def get_agent_roles(cls, knobs: dict[str, Any] | None) -> list[AgentRole]:
        """Return agent IDs and display names for the given knobs configuration.

        Used by the web API to populate the per-agent model override UI
        before a simulation starts. Must not require a scenario instance.
        """
        ...

    @classmethod
    @abstractmethod
    def knobs_json_schema(cls) -> dict[str, Any]:
        """Return the JSON Schema for this scenario's knobs Pydantic model.

        Used by the MCP server to expose available configuration fields,
        their types, enum values, and descriptions to LLM clients.
        """
        ...

    @classmethod
    def prepare_config(cls, config: dict[str, Any]) -> dict[str, Any]:
        """Transform raw CLI config before passing to ``create_from_config``.

        Scenarios override this to resolve file-path references into
        loaded data. For example, a scenario that needs a data file can
        accept a file path string in the config and load it here.

        The default is a no-op pass-through.
        """
        return config

    @classmethod
    def create_from_config(cls, config: dict[str, Any]) -> Self:
        """Reconstruct a scenario from its serialized config dict.

        Callers use this for both validation and reconstruction:
        - ``run`` preflight (CLI and API) to validate prepared config payloads
        - ``evaluate`` to rebuild the scenario from JSONL-stored config
        - fork/resume flows to reconstruct scenarios from persisted state

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
    def get_agents(self, default_model: str, default_provider: str) -> list[AgentConfig]:
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
    def get_world(self) -> ScenarioWorld:
        """Return a living world simulation to run alongside agents.

        The world runs as its own asyncio task and receives message events
        and round advance signals. It can push notifications to agents
        via the world context.
        """
        ...

    @abstractmethod
    def get_mcp_tools(self) -> list[ScenarioMcpTool]:
        """Return scenario-specific tools to register on the MCP server.

        Each tool is exposed alongside the base communication tools
        (read_notifications, read_channel, send_message, etc.). Return an
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

    def validate_outgoing_message(self, agent_id: str, channel_id: str) -> str | None:
        """Validate whether an agent is allowed to send to a channel right now.

        Called by the ``send_message`` MCP tool before storing the message.
        Returns an error string if the message should be rejected, or None
        to allow it. The default allows all messages.
        """
        _ = agent_id, channel_id
        return None

    def get_primary_channel_id(self) -> str | None:
        """Return the channel ID that evaluators should focus on.

        The primary channel is where the core task happens under constraints.
        Evaluators prioritize language phenomena observed here. Returns None
        if no single channel is primary.
        """
        return None

    def transform_outgoing_message(self, agent_id: str, channel_id: str, text: str) -> str:
        """Transform a message before it is stored and delivered to the channel.

        Called by the ``send_message`` MCP tool after validation but before
        the message is appended. The agent sees the transformed text in
        subsequent ``read_channel`` calls, not the original.

        The default returns the text unchanged.
        """
        _ = agent_id, channel_id
        return text

    def get_postmortem_injection(self, round_number: int, agent_id: str) -> str | None:
        """Return postmortem text for an agent after the given round completes.

        The game clock calls this after agents go idle in a round. If any agent
        returns a non-None value, the game clock enters a postmortem phase
        before advancing to the next round. The default returns None (no postmortem).
        """
        _ = round_number, agent_id
        return None

    def get_max_postmortem_duration_seconds(self) -> float:
        """Return the maximum wall-clock seconds a postmortem phase may last.

        The game clock uses this as the timeout for the postmortem discussion.
        Override to make the duration configurable via scenario knobs.
        """
        return 60.0

    def on_postmortem_started(self, round_number: int) -> None:
        """Called by the game clock when a postmortem phase begins after a round.

        Scenarios use this to update internal state (e.g. unlock discussion
        channels). The default is a no-op.
        """
        _ = round_number

    async def on_round_advanced(self, round_number: int) -> None:
        """Called by the game clock after advancing to a new round.

        Scenarios with mutable world state override this to resolve pending
        actions (effort allocations, status updates) and advance the simulation.
        The default is a no-op for scenarios without world state.
        """
        _ = round_number
