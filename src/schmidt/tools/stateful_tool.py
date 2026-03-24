"""Base for tools that read or mutate simulation state.

Provides ``StatefulToolExecutor`` which handles the validate-apply-log-respond cycle
for scenario tools that interact with ``SimulationStateProtocol``. Ensures ground truth
is always captured even when the agent sees a filtered response.
"""

import logging

from schmidt.event_logger import EventLogger
from schmidt.models.event import AgentActionApplied
from schmidt.simulation_state_protocol import AgentAction, SimulationStateProtocol

logger = logging.getLogger(__name__)


class StatefulToolExecutor:
    """Wraps tool functions that need access to mutable simulation state.

    Scenario tools delegate to ``execute_action`` which applies the action to the
    world state, logs the full ground truth outcome as an ``AgentActionApplied``
    event, and returns only the agent-visible result string.
    """

    def __init__(
        self,
        state: SimulationStateProtocol,
        event_logger: EventLogger,
    ) -> None:
        self._state = state
        self._event_logger = event_logger

    async def execute_action(
        self,
        agent_id: str,
        action: AgentAction,
    ) -> str:
        """Apply a structured action and return the agent-visible result.

        Logs an ``AgentActionApplied`` event capturing the full ground truth delta
        regardless of what the agent is shown.
        """
        outcome = self._state.apply_agent_action(agent_id=agent_id, action=action)

        await self._event_logger.log(
            event=AgentActionApplied(
                agent_id=agent_id,
                action_type=action.action_type,
                parameters=action.parameters,
                outcome=outcome.model_dump(mode="json"),
            )
        )

        logger.debug(
            "Agent %s applied action %s (success=%s)",
            agent_id,
            action.action_type,
            outcome.success,
        )

        return outcome.agent_visible_result
