"""Built-in send_message tool that allows agents to post messages
to channels via the ChannelRouter.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import uuid4

from schmidt.channel_router import ChannelRouter
from schmidt.event_logger import EventLogger
from schmidt.models.event import MessageSent
from schmidt.models.message import SimulationMessage
from schmidt.models.tool_definition import ToolParameter, ToolSpec

logger = logging.getLogger(__name__)

SEND_MESSAGE_SPEC = ToolSpec(
    name="send_message",
    description="Send a message to a channel you are a member of.",
    parameters=[
        ToolParameter(
            name="channel_id",
            param_type="string",
            description="The ID of the channel to send the message to.",
            required=True,
        ),
        ToolParameter(
            name="text",
            param_type="string",
            description="The text content of the message.",
            required=True,
        ),
    ],
)


def create_send_message_executor(
    channel_router: ChannelRouter,
    event_logger: EventLogger,
) -> Callable[..., Awaitable[str]]:
    """Return an async executor function that sends messages through the given ChannelRouter.

    The returned coroutine validates that the agent is a member of the target channel
    before creating and appending a SimulationMessage. It also logs a MessageSent event
    with the same message_id stored in the channel.
    """

    async def send_message(agent_id: str, channel_id: str, text: str) -> str:
        """Send a message to a channel on behalf of an agent.

        Raises ValueError if the agent is not a member of the specified channel.
        Attempts to normalize channel IDs that start with '#' by stripping the prefix.
        """
        if not channel_router.validate_membership(agent_id=agent_id, channel_id=channel_id):
            if channel_id.startswith("#"):
                stripped = channel_id[1:]
                if channel_router.validate_membership(agent_id=agent_id, channel_id=stripped):
                    logger.debug(
                        "Normalized channel_id '%s' to '%s' for agent %s",
                        channel_id,
                        stripped,
                        agent_id,
                    )
                    channel_id = stripped
                else:
                    raise ValueError(
                        f"Agent '{agent_id}' is not a member of channel '{channel_id}'"
                    )
            else:
                raise ValueError(f"Agent '{agent_id}' is not a member of channel '{channel_id}'")

        message = SimulationMessage(
            message_id=str(uuid4()),
            channel_id=channel_id,
            sender_agent_id=agent_id,
            text=text,
            timestamp=datetime.now(tz=UTC),
        )
        channel_router.append_message(message=message)

        await event_logger.log(event=MessageSent(message=message))

        logger.debug("Agent %s sent message to channel %s", agent_id, channel_id)
        return f"Message sent to channel '{channel_id}'"

    return send_message
