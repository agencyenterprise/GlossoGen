"""The base communication tools, built as executors over the runtime.

Every agent is offered these unless the scenario withholds one through
``hidden_base_tools``. ``send_message`` is the scenario's
``send_message_executor`` and ``read_notifications`` lives in
``glossogen.runners.read_notifications_tool``; the three built here read
channels and memberships. Each executor takes ``agent_id`` first, as a scenario
tool's does, and refuses with ``ValueError``, which the runner hands the agent
as the tool's error.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from glossogen.elapsed_time import elapsed_seconds_since_start
from glossogen.models.mcp_responses import ChannelMessage, ReadChannelResult
from glossogen.runtime.read_notifications_schema import READ_NOTIFICATIONS_TOOL_NAME
from glossogen.runtime.simulation_state import SimulationRuntime

READ_CHANNEL_TOOL_NAME = "read_channel"
SEND_MESSAGE_TOOL_NAME = "send_message"
LIST_CHANNELS_TOOL_NAME = "list_channels"
GET_CHANNEL_MEMBERS_TOOL_NAME = "get_channel_members"

BASE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        READ_NOTIFICATIONS_TOOL_NAME,
        READ_CHANNEL_TOOL_NAME,
        SEND_MESSAGE_TOOL_NAME,
        LIST_CHANNELS_TOOL_NAME,
        GET_CHANNEL_MEMBERS_TOOL_NAME,
    }
)
"""The tools every agent is offered unless the scenario withholds one."""

READ_CHANNEL_DESCRIPTION = (
    "Read the last N messages from a channel. Each message includes the name of the "
    "agent who sent it, so you can always tell who said what without them identifying "
    "themselves, and an elapsed_seconds value giving the time it was sent as seconds "
    "since the simulation began."
)
LIST_CHANNELS_DESCRIPTION = "See which channels you have access to."
GET_CHANNEL_MEMBERS_DESCRIPTION = "See who is in a channel."


def build_read_channel(runtime: SimulationRuntime) -> Callable[..., Awaitable[dict[str, Any]]]:
    """The ``read_channel`` executor: recent messages, advancing the agent's read position."""

    async def read_channel(agent_id: str, channel_id: str, last_n: int) -> dict[str, Any]:
        if not runtime.channel_router.validate_membership(agent_id=agent_id, channel_id=channel_id):
            raise ValueError(f"You are not a member of channel '{channel_id}'")
        session = runtime.resolve_session(agent_id=agent_id)
        visible = runtime.channel_router.get_visible_history(
            channel_id=channel_id, agent_id=agent_id
        )
        # Messages visible at read time are not flagged as new by a later
        # send_message conflict check.
        session.record_channel_read(
            channel_id=channel_id,
            message_count=runtime.channel_router.get_message_count(channel_id=channel_id),
        )
        return ReadChannelResult(
            current_round=runtime.current_round,
            messages=[
                ChannelMessage(
                    round=msg.round_number,
                    sender=msg.sender_display_name,
                    text=msg.text,
                    elapsed_seconds=elapsed_seconds_since_start(
                        when=msg.timestamp,
                        start=runtime.simulation_start_time,
                    ),
                )
                for msg in visible[-last_n:]
            ],
        ).model_dump()

    return read_channel


def build_list_channels(
    runtime: SimulationRuntime,
) -> Callable[..., Awaitable[list[dict[str, str]]]]:
    """The ``list_channels`` executor: the agent's channels with display names."""

    async def list_channels(agent_id: str) -> list[dict[str, str]]:
        return [
            {
                "channel_id": channel_id,
                "display_name": runtime.scenario.get_channel_display_name(
                    channel_id=channel_id, agent_id=agent_id
                ),
            }
            for channel_id in runtime.channel_router.get_agent_channel_ids(agent_id=agent_id)
        ]

    return list_channels


def build_get_channel_members(
    runtime: SimulationRuntime,
) -> Callable[..., Awaitable[list[dict[str, str]]]]:
    """The ``get_channel_members`` executor: a channel's members with display names."""

    async def get_channel_members(agent_id: str, channel_id: str) -> list[dict[str, str]]:
        if not runtime.channel_router.validate_membership(agent_id=agent_id, channel_id=channel_id):
            raise ValueError(f"You are not a member of channel '{channel_id}'")
        return [
            {
                "agent_id": member_id,
                "display_name": runtime.scenario.get_agent_display_name_at_round(
                    agent_id=member_id, round_number=runtime.current_round
                ),
            }
            for member_id in runtime.channel_router.get_channel_member_ids(channel_id=channel_id)
        ]

    return get_channel_members
