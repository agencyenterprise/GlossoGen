"""MCP tool definitions for the simulation runtime.

Registers tools on a FastMCP server that agents call to interact with the
shared simulation world. Agent identity is resolved from the MCP connection
context (HTTP query parameter), not from tool arguments.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

from schmidt.models.event import MessageSent
from schmidt.models.mcp_responses import ChannelMessage, SendMessageResult
from schmidt.models.message import SimulationMessage
from schmidt.runtime.activity_notification import NewMessagesNotification
from schmidt.runtime.agent_session import AgentSession
from schmidt.runtime.scenario_mcp_tool import ToolContext
from schmidt.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)

HIDDEN_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "check_messages",
        "read_channel",
        "send_message",
        "list_channels",
        "get_channel_members",
        "ToolSearch",
    }
)
"""Tool names filtered out of the frontend timeline.

Includes base communication tools (whose effects are visible as chat messages)
and Claude Code SDK infrastructure tools (like ToolSearch).
"""


def _resolve_agent_from_context(ctx: ToolContext, runtime: SimulationRuntime) -> AgentSession:
    """Extract agent_id from the MCP request's query parameters and return the session.

    Agent identity is embedded in the Streamable HTTP connection URL
    (e.g. ``http://localhost:8001/mcp?agent_id=engineer``). If the MCP
    transport does not provide an HTTP request (e.g. stdio transport),
    this raises a clear error.
    """
    request = ctx.request_context.request
    if request is None:
        raise ValueError(
            "Cannot resolve agent identity: no HTTP request in MCP context. "
            "Agent identity requires Streamable HTTP transport with ?agent_id= query parameter."
        )
    agent_id = request.query_params.get("agent_id")
    if agent_id is None:
        raise ValueError(
            "Cannot resolve agent identity: missing ?agent_id= query parameter "
            f"on MCP connection URL. Request path: {request.url.path}"
        )
    return runtime.resolve_session(agent_id=agent_id)


def register_tools(mcp: FastMCP, runtime: SimulationRuntime) -> None:
    """Register all simulation MCP tools on the given FastMCP server.

    Registers the five base communication tools plus any scenario-specific
    tools returned by ``scenario.get_mcp_tools()``.
    """

    @mcp.tool(
        name="check_messages",
        description="Check if there are any new messages or updates for you.",
    )
    async def check_messages(ctx: ToolContext) -> dict[str, Any]:
        """Block until there is activity for the agent, then return it.

        For NewMessagesNotifications, filters out channels the agent has
        already read (last_seen >= actual count). If all channels in a
        notification are stale, the notification is discarded and the agent
        continues waiting for the next one.

        Returns a no-activity response after 30 seconds of silence so agents
        are not stuck waiting indefinitely.
        """
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        while True:
            try:
                notification = await asyncio.wait_for(
                    session.wait_for_notification(),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                session.is_idle = False
                logger.info(
                    "Agent %s check_messages timed out after 30s, returning no_activity",
                    session.agent_id,
                )
                return {"type": "no_activity", "detail": "No new messages."}
            if isinstance(notification, NewMessagesNotification):
                fresh_channels = [
                    ch
                    for ch in notification.channels
                    if runtime.channel_router.get_message_count(channel_id=ch)
                    > session.get_last_seen_count(channel_id=ch)
                ]
                if not fresh_channels:
                    logger.debug(
                        "Agent %s skipping stale notification (all channels already read)",
                        session.agent_id,
                    )
                    continue
                notification = NewMessagesNotification(channels=fresh_channels)
                for ch in fresh_channels:
                    session.record_channel_read(
                        channel_id=ch,
                        message_count=runtime.channel_router.get_message_count(
                            channel_id=ch,
                        ),
                    )
            delay = session.sample_reaction_delay()
            logger.info(
                "Agent %s received %s, applying %.2fs reaction delay",
                session.agent_id,
                notification.type.value,
                delay,
            )
            await asyncio.sleep(delay)
            return notification.model_dump()

    @mcp.tool(
        name="read_channel",
        description="Read the last N messages from a channel.",
    )
    async def read_channel(ctx: ToolContext, channel_id: str, last_n: int) -> list[dict[str, Any]]:
        """Return recent messages and advance the agent's read position.

        Updates last_seen so that messages visible at read time are not
        flagged as new in subsequent send_message conflict checks.
        """
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        agent_id = session.agent_id
        if not runtime.channel_router.validate_membership(
            agent_id=agent_id,
            channel_id=channel_id,
        ):
            raise ValueError(f"You are not a member of channel '{channel_id}'")
        history = runtime.channel_router.get_history(channel_id=channel_id)
        session.record_channel_read(
            channel_id=channel_id,
            message_count=len(history),
        )
        recent = history[-last_n:]
        display_name_fn = runtime.scenario.get_agent_display_name
        return [
            {
                "sender": display_name_fn(agent_id=msg.sender_agent_id),
                "text": msg.text,
                "timestamp": msg.timestamp.isoformat(),
            }
            for msg in recent
        ]

    @mcp.tool(
        name="send_message",
        description=(
            "Send a message to a channel. "
            "If new messages arrived since your last read_channel call, "
            "the send is held and the new messages are returned so you can decide what to do. "
            "Set force=true to send regardless of new messages."
        ),
    )
    async def send_message(
        ctx: ToolContext, channel_id: str, text: str, force: bool
    ) -> dict[str, Any]:
        """Post a message with optimistic concurrency control."""
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        agent_id = session.agent_id
        if not runtime.channel_router.validate_membership(
            agent_id=agent_id,
            channel_id=channel_id,
        ):
            raise ValueError(f"You are not a member of channel '{channel_id}'")

        display_name_fn = runtime.scenario.get_agent_display_name

        async with runtime.get_channel_lock(channel_id=channel_id):
            actual_count = runtime.channel_router.get_message_count(
                channel_id=channel_id,
            )
            last_seen = session.get_last_seen_count(channel_id=channel_id)

            if not force and actual_count > last_seen:
                history = runtime.channel_router.get_history(channel_id=channel_id)
                unseen = history[last_seen:]
                new_messages = [
                    ChannelMessage(
                        sender=display_name_fn(agent_id=msg.sender_agent_id),
                        text=msg.text,
                        timestamp=msg.timestamp.isoformat(),
                    )
                    for msg in unseen
                ]
                logger.info(
                    "Agent %s send_message conflict on channel %s: "
                    "last_seen=%d actual=%d (%d new)",
                    agent_id,
                    channel_id,
                    last_seen,
                    actual_count,
                    len(unseen),
                )
                return SendMessageResult(
                    status="conflict",
                    detail=(
                        f"{len(unseen)} new message(s) arrived since your last read. "
                        "Review them and either revise your message or re-send with force=true."
                    ),
                    new_messages=new_messages,
                ).model_dump()

            message = SimulationMessage(
                message_id=str(uuid4()),
                channel_id=channel_id,
                sender_agent_id=agent_id,
                text=text,
                timestamp=datetime.now(tz=UTC),
            )
            runtime.channel_router.append_message(message=message)
            await runtime.event_logger.log(event=MessageSent(message=message))

            session.record_channel_read(
                channel_id=channel_id,
                message_count=actual_count + 1,
            )

            member_ids = runtime.channel_router.get_channel_member_ids(
                channel_id=channel_id,
            )
            for member_id in member_ids:
                if member_id == agent_id:
                    continue
                member_session = runtime.agent_sessions.get(member_id)
                if member_session is not None:
                    member_session.push_notification(
                        notification=NewMessagesNotification(channels=[channel_id]),
                    )

            runtime.fire_on_message_callbacks()

        logger.info("Agent %s sent %d chars to channel %s", agent_id, len(text), channel_id)
        return SendMessageResult(
            status="sent",
            detail=f"Message sent to channel '{channel_id}'",
            new_messages=[],
        ).model_dump()

    @mcp.tool(
        name="list_channels",
        description="See which channels you have access to.",
    )
    async def list_channels(ctx: ToolContext) -> list[dict[str, str]]:
        """Return the channels the agent belongs to with display names."""
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        agent_id = session.agent_id
        channel_ids = runtime.channel_router.get_agent_channel_ids(agent_id=agent_id)
        return [
            {
                "channel_id": cid,
                "display_name": runtime.scenario.get_channel_display_name(
                    channel_id=cid,
                    agent_id=agent_id,
                ),
            }
            for cid in channel_ids
        ]

    @mcp.tool(
        name="get_channel_members",
        description="See who is in a channel.",
    )
    async def get_channel_members(ctx: ToolContext, channel_id: str) -> list[dict[str, str]]:
        """Return the members of a channel with display names."""
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        agent_id = session.agent_id
        if not runtime.channel_router.validate_membership(
            agent_id=agent_id,
            channel_id=channel_id,
        ):
            raise ValueError(f"You are not a member of channel '{channel_id}'")
        member_ids = runtime.channel_router.get_channel_member_ids(channel_id=channel_id)
        return [
            {
                "agent_id": mid,
                "display_name": runtime.scenario.get_agent_display_name(agent_id=mid),
            }
            for mid in member_ids
        ]

    # Register scenario-specific tools. Executors accept ctx: ToolContext
    # directly; FastMCP auto-injects it and hides it from the tool schema.
    for scenario_tool in runtime.scenario.get_mcp_tools():
        mcp.tool(
            name=scenario_tool.name,
            description=scenario_tool.description,
        )(scenario_tool.executor)
        logger.info("Registered scenario MCP tool: %s", scenario_tool.name)
