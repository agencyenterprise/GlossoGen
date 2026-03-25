"""Built-in think tool that lets agents record private reasoning within
their normal turn, without a separate LLM call.
"""

import logging
from collections.abc import Awaitable, Callable

from schmidt.event_logger import EventLogger
from schmidt.models.event import ReasoningCaptured
from schmidt.models.tool_definition import ToolParameter, ToolSpec

logger = logging.getLogger(__name__)

THINK_SPEC = ToolSpec(
    name="think",
    description=(
        "Record your private reasoning. Use this to think through your "
        "situation before acting: what you know, your concerns, and your plan. "
        "This is NOT visible to other agents."
    ),
    parameters=[
        ToolParameter(
            name="reasoning",
            param_type="string",
            description="Your private reasoning about the current situation and planned actions.",
            required=True,
        ),
    ],
)


def create_think_executor(
    event_logger: EventLogger,
    round_number_getter: Callable[[], int],
) -> Callable[..., Awaitable[str]]:
    """Return an async executor that logs a ReasoningCaptured event.

    The reasoning text is recorded in the event log for evaluation and
    interpretability but is never shared with other agents.
    """

    async def think(agent_id: str, reasoning: str) -> str:
        """Record an agent's private reasoning."""
        round_number = round_number_getter()
        await event_logger.log(
            event=ReasoningCaptured(
                agent_id=agent_id,
                round_number=round_number,
                reasoning_text=reasoning,
            )
        )
        logger.debug(
            "Agent %s recorded reasoning (round %d, %d chars)",
            agent_id,
            round_number,
            len(reasoning),
        )
        return "Reasoning recorded."

    return think
