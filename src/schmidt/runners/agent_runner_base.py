"""Abstract base class for agent runners.

An agent runner launches and manages a single autonomous agent that connects
to the simulation runtime via MCP.  Concrete implementations wrap a specific
agentic runtime (Claude Code, Codex, Gemini, etc.).
"""

from abc import ABC, abstractmethod

from schmidt.event_logger import EventLogger
from schmidt.models.agent_config import AgentConfig
from schmidt.runners.agent_run_result import AgentRunResult


class AgentRunner(ABC):
    """Launches an autonomous agent connected to the MCP server.

    Each runner instance handles one agent. The agent shuts down when
    the MCP server sends a done notification via ``read_notifications``.
    """

    @abstractmethod
    async def start(
        self,
        agent_config: AgentConfig,
        mcp_server_url: str,
        event_logger: EventLogger,
        cost_tracker: dict[str, float],
    ) -> AgentRunResult:
        """Start the agent. Blocks until the agent finishes.

        ``cost_tracker`` is a shared dict keyed by ``agent_id`` that the runner
        must update after each completed cycle so the supervisor can recover
        the agent's last known cost even if its task is cancelled on shutdown.
        """
        ...
