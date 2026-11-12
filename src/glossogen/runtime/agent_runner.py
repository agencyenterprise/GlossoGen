"""The interface the supervisor drives agent runners through.

A runner launches and manages one autonomous agent, which calls the runtime's
tools in its own process and decides for itself when to act. The runtime owns
this interface so a different agent framework can be dropped in without the
supervisor knowing; ``glossogen.runners.pydantic_ai_runner.PydanticAIRunner``
is the only implementation today, and the entry point hands the supervisor a
factory for it.
"""

from abc import ABC, abstractmethod

from glossogen.models.agent_config import AgentConfig
from glossogen.runtime.agent_run_result import AgentRunResult
from glossogen.runtime.simulation_state import SimulationRuntime

CLOSING_PROMPT_TIMEOUT_SECONDS = 300.0
"""The longest a runner may take over the closing prompt, retries included.

Past it the agent goes unasked. The supervisor waits this long, past its drain
time, for runners to finish once the run has completed.
"""


class AgentRunner(ABC):
    """Launches an autonomous agent over the runtime's tools.

    Each runner instance handles one agent. The agent shuts down when the
    runtime sends a done notification via ``read_notifications``.
    """

    @abstractmethod
    async def start(
        self,
        agent_config: AgentConfig,
        runtime: SimulationRuntime,
        cost_tracker: dict[str, float],
    ) -> AgentRunResult:
        """Start the agent. Blocks until the agent finishes.

        ``cost_tracker`` is a shared dict keyed by ``agent_id`` that the runner
        adds each completed cycle's cost to, so the supervisor can recover the
        seat's spend even if its task is cancelled on shutdown. A seat swapped
        mid-run keeps its predecessor's spend, since the successor adds to it.
        """
        ...
