"""Abstract base class that every simulation scenario must implement."""

from abc import ABC, abstractmethod

from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel
from schmidt.models.simulation_state import SimulationState, TurnDecision
from schmidt.tools.tool_registry import ToolRegistry


class SimulationScenario(ABC):
    """Contract that a scenario plug-in must fulfil to be run by the simulation hub.

    Each concrete subclass defines the agents, channels, turn logic, prompt
    injections, and tools that comprise a single simulation scenario.
    """

    @abstractmethod
    def name(self) -> str:
        """Return the unique identifier for this scenario."""
        ...

    @abstractmethod
    def get_agents(self) -> list[AgentConfig]:
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
