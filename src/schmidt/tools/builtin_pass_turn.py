"""Built-in pass_turn tool that allows agents to explicitly decline
speaking on their turn.
"""

import logging
from collections.abc import Awaitable, Callable

from schmidt.event_logger import EventLogger
from schmidt.models.event import TurnPassed
from schmidt.models.tool_definition import ToolParameter, ToolSpec

logger = logging.getLogger(__name__)

PASS_TURN_SPEC = ToolSpec(
    name="pass_turn",
    description=(
        "Decline to send a message on this turn. "
        "Call this when you have nothing to add to the conversations."
    ),
    parameters=[
        ToolParameter(
            name="reason",
            param_type="string",
            description="Brief explanation of why you are passing.",
            required=True,
        ),
    ],
)


def create_pass_turn_executor(
    event_logger: EventLogger,
) -> Callable[..., Awaitable[str]]:
    """Return an async executor function that logs a TurnPassed event.

    The returned coroutine records the agent's decision to pass and
    the reason provided.
    """

    async def pass_turn(agent_id: str, reason: str) -> str:
        """Record that an agent chose to pass on their turn."""
        await event_logger.log(
            event=TurnPassed(
                agent_id=agent_id,
                reason=reason,
            )
        )
        logger.debug("Agent %s passed turn: %s", agent_id, reason)
        return "Turn passed successfully."

    return pass_turn
