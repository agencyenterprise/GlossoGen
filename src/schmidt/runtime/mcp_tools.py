"""MCP tool definitions for the simulation runtime.

Registers tools on a FastMCP server that agents call to interact with the
shared simulation world. Agent identity is resolved from the MCP connection
context (HTTP query parameter), not from tool arguments. Scenario-specific
tools are wrapped with an authorization guard that checks the per-agent
allowlist in ``SimulationRuntime`` before dispatching.
"""

# FastMCP tool handlers below are registered via ``@mcp.tool(...)``;
# pyright can't see the framework's runtime use of them.
# pyright: reportUnusedFunction=false

import asyncio
import functools
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

from schmidt.elapsed_time import elapsed_seconds_since_start
from schmidt.models.event import MessageSent
from schmidt.models.mcp_responses import ChannelMessage, ReadChannelResult, SendMessageResult
from schmidt.models.message import SimulationMessage
from schmidt.runtime.activity_notification import (
    ActivityNotification,
    NewMessagesNotification,
    NoActivityNotification,
)
from schmidt.runtime.agent_session import AgentSession
from schmidt.runtime.scenario_mcp_tool import ToolContext, resolve_agent_id
from schmidt.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)

PARALLEL_DETECTION_WINDOW_SECONDS = 0.5
"""How recently another tool must have dispatched for ``read_notifications`` to
treat itself as part of the same parallel turn and reject. Sized to comfortably
exceed the gap between sibling parallel dispatches (microseconds in practice)
while staying well under the LLM's sequential round-trip time (hundreds of ms
to seconds), so legitimate sequential ``read_notifications`` calls are not
falsely rejected."""

NON_BLOCKING_TOOL_TIMEOUT_SECONDS = 120.0
"""Hard cap on any single non-blocking tool body (scenario tools, send_message,
read_channel). Sits well under the MCP client's ~300s request timeout so a
stalled call (e.g. a judge HTTP request that hangs) is cancelled server-side,
releasing the agent's in-flight slot and returning a clean error to the agent
instead of wedging it for the rest of the round."""

STALE_ACTIVE_CALL_SECONDS = 150.0
"""Age past which an in-flight non-blocking call is treated as a zombie by
``read_notifications``. Above ``NON_BLOCKING_TOOL_TIMEOUT_SECONDS`` so it only
trips when a call somehow survives the hard cap; lets ``read_notifications``
proceed so the agent can always drain its queue and recover."""

BASE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "read_notifications",
        "read_channel",
        "send_message",
        "list_channels",
        "get_channel_members",
    }
)
"""Base communication tools available to all agents unconditionally.

These are always visible in ``tools/list`` and exempt from the per-agent
authorization guard.
"""


def _build_notification_payload(
    notification: ActivityNotification,
    session: AgentSession,
    current_round: int,
) -> dict[str, Any]:
    """Serialize a notification with queue depth and the current simulation round.

    ``pending_count`` tells the agent how many additional notifications are
    still queued after this one is consumed. ``current_round`` is the round
    the simulation is in at delivery time so the agent can recognise that
    instructions seen on a channel before the current round are stale —
    each ``read_channel`` and ``send_message`` response carries the same
    field, providing a consistent reference everywhere the agent looks.
    """
    payload = notification.model_dump()
    payload["pending_count"] = session.pending_notifications_count()
    payload["current_round"] = current_round
    return payload


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


def _reject_if_terminated(session: AgentSession, tool_name: str) -> None:
    """Raise if the calling agent's session has been drained for a swap.

    Once ``DoneNotification`` is queued on an ``AgentSession``, the agent
    is being torn down to make room for its swapped-in successor. Any
    state-mutating tool call from a runner that has not yet noticed the
    Done signal would land under the new round / new occupant context
    and corrupt the simulation, so this check rejects them at the MCP
    boundary. ``read_notifications`` is exempt — the dying runner must
    still be able to read its Done signal to exit cleanly.
    """
    if session.terminated:
        raise ValueError(
            f"Agent '{session.agent_id}' is being swapped out; "
            f"tool '{tool_name}' rejected. Read your notifications to exit cleanly."
        )


def _build_guarded_executor(
    tool_name: str,
    original_executor: Callable[..., Awaitable[str]],
    runtime: SimulationRuntime,
) -> Callable[..., Awaitable[str]]:
    """Wrap a scenario tool executor with a per-agent authorization check.

    The returned wrapper resolves the calling agent's identity from the MCP
    request context, then checks ``runtime.is_tool_allowed()`` before
    delegating to the original executor. Unauthorized calls raise a
    ``ValueError`` that FastMCP surfaces as a tool error to the agent.

    The wrapper preserves the original function's signature so that
    FastMCP can introspect parameter names and types for the tool schema.
    """

    @functools.wraps(original_executor)
    async def _guarded(*args: Any, **kwargs: Any) -> str:
        ctx_arg: ToolContext = kwargs.get("ctx") or args[0]
        agent_id = resolve_agent_id(ctx=ctx_arg)
        if not runtime.is_tool_allowed(agent_id=agent_id, tool_name=tool_name):
            logger.warning(
                "Agent %s unauthorized call to tool %s",
                agent_id,
                tool_name,
            )
            raise ValueError(f"Agent '{agent_id}' is not authorized to call tool '{tool_name}'")
        session = runtime.resolve_session(agent_id=agent_id)
        _reject_if_terminated(session=session, tool_name=tool_name)
        async with session.track_active_call():
            try:
                return await asyncio.wait_for(
                    original_executor(*args, **kwargs),
                    timeout=NON_BLOCKING_TOOL_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.exception(
                    "Tool %s for agent %s exceeded %.0fs and was cancelled to free the agent",
                    tool_name,
                    agent_id,
                    NON_BLOCKING_TOOL_TIMEOUT_SECONDS,
                )
                return (
                    f"The '{tool_name}' action timed out after "
                    f"{NON_BLOCKING_TOOL_TIMEOUT_SECONDS:.0f} seconds and was cancelled. "
                    "Try again."
                )

    # Preserve the original signature so FastMCP generates the correct
    # JSON schema for the tool's parameters.
    _guarded.__signature__ = inspect.signature(original_executor)  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
    return _guarded


def register_tools(mcp: FastMCP, runtime: SimulationRuntime) -> None:
    """Register all simulation MCP tools on the given FastMCP server.

    Registers the five base communication tools plus any scenario-specific
    tools returned by ``scenario.get_mcp_tools()``.
    """

    @mcp.tool(
        name="read_notifications",
        description=(
            "Read the latest updates from the world: new messages, events, or status. "
            "Must be called on its own — never in parallel with another tool call. "
            "Issue any other tool calls first, see their results, then call read_notifications. "
            "The response includes a pending_count field indicating how many additional "
            "notifications are still queued. If pending_count > 0, you must call "
            "read_notifications again after handling the current one to drain the queue."
        ),
    )
    async def read_notifications(
        ctx: ToolContext,
    ) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        """Block until there is activity for the agent, then return it.

        For NewMessagesNotifications, filters out channels the agent has
        already read (last_seen >= actual count). If all channels in a
        notification are stale, the notification is discarded and the agent
        continues waiting for the next one.

        Returns a no-activity response after 120 seconds of silence so agents
        are not stuck waiting indefinitely.

        Rejects parallel invocation: when the LLM dispatches
        ``read_notifications`` alongside other tool calls in the same turn,
        the parallel call would block the cycle from reacting to the
        sibling tools' results until either a new notification arrives or
        the 120s timeout fires. To force the LLM to sequence calls, this
        function returns ``no_activity`` immediately when another
        non-blocking call is in flight, or another ``read_notifications``
        is already pending, for the same agent.
        """
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        # Brief yield so parallel sibling tools have a chance to enter
        # ``track_active_call`` and stamp the dispatch timestamp before
        # we check. Without this wait, a ``read_notifications`` scheduled
        # ahead of its siblings would see no recent activity and proceed.
        await asyncio.sleep(0.05)
        now = time.monotonic()
        last_dispatch = session.last_non_blocking_dispatch_ts
        sibling_dispatched_recently = (
            last_dispatch is not None and (now - last_dispatch) < PARALLEL_DETECTION_WINDOW_SECONDS
        )
        # A non-blocking call that has been in flight far longer than any
        # legitimate tool body is a zombie (e.g. a stalled judge HTTP call
        # whose cancellation did not unwind). Treat it as not-blocking so the
        # agent is never starved of its notification queue and can recover.
        oldest_active_age = session.oldest_active_call_age(now=now)
        active_calls_are_stale = (
            oldest_active_age is not None and oldest_active_age >= STALE_ACTIVE_CALL_SECONDS
        )
        genuine_parallel_call = session.active_non_blocking_calls > 0 and not active_calls_are_stale
        if (
            genuine_parallel_call
            or session.read_notifications_in_flight
            or sibling_dispatched_recently
        ):
            logger.info(
                "Agent %s read_notifications rejected: parallel call detected "
                "(active_non_blocking_calls=%d, rn_in_flight=%s, "
                "sibling_dispatched_recently=%s)",
                session.agent_id,
                session.active_non_blocking_calls,
                session.read_notifications_in_flight,
                sibling_dispatched_recently,
            )
            return _build_notification_payload(
                notification=NoActivityNotification(
                    detail=(
                        "read_notifications cannot be issued in parallel with other tool "
                        "calls. Wait for your other tool calls to return, observe their "
                        "results, then call read_notifications by itself in the next turn."
                    ),
                ),
                session=session,
                current_round=runtime.current_round,
            )
        session.read_notifications_in_flight = True
        try:
            return await _await_notification_loop(session=session, runtime=runtime)
        finally:
            session.read_notifications_in_flight = False

    async def _await_notification_loop(
        session: AgentSession,
        runtime: SimulationRuntime,
    ) -> dict[str, Any]:
        """Wait for the next activity notification, returning ``no_activity`` on timeout."""
        while True:
            try:
                notification = await asyncio.wait_for(
                    session.wait_for_notification(),
                    timeout=120.0,
                )
            except asyncio.TimeoutError:
                session.is_idle = False
                logger.info(
                    "Agent %s read_notifications timed out after 120s, returning no_activity",
                    session.agent_id,
                )
                return _build_notification_payload(
                    notification=NoActivityNotification(detail="No new messages."),
                    session=session,
                    current_round=runtime.current_round,
                )
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
            return _build_notification_payload(
                notification=notification,
                session=session,
                current_round=runtime.current_round,
            )

    @mcp.tool(
        name="read_channel",
        description=(
            "Read the last N messages from a channel. Each message includes the name of the "
            "agent who sent it, so you can always tell who said what without them identifying "
            "themselves, and an elapsed_seconds value giving the time it was sent as seconds "
            "since the simulation began."
        ),
    )
    async def read_channel(
        ctx: ToolContext, channel_id: str, last_n: int
    ) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        """Return recent messages and advance the agent's read position.

        Updates last_seen so that messages visible at read time are not
        flagged as new in subsequent send_message conflict checks.
        """
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        _reject_if_terminated(session=session, tool_name="read_channel")
        async with session.track_active_call():
            agent_id = session.agent_id
            if not runtime.channel_router.validate_membership(
                agent_id=agent_id,
                channel_id=channel_id,
            ):
                raise ValueError(f"You are not a member of channel '{channel_id}'")
            visible = runtime.channel_router.get_visible_history(
                channel_id=channel_id,
                agent_id=agent_id,
            )
            absolute_count = runtime.channel_router.get_message_count(channel_id=channel_id)
            session.record_channel_read(
                channel_id=channel_id,
                message_count=absolute_count,
            )
            recent = visible[-last_n:]
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
                    for msg in recent
                ],
            ).model_dump()

    @mcp.tool(
        name="send_message",
        description=(
            "Send a message to a channel. Every member of the channel sees it attributed to you "
            "by name, so you do not need to sign your messages or state who you are. "
            "If new messages arrived since your last read_channel call, "
            "the send is held and the new messages are returned so you can decide what to do. "
            "Set force=true to send regardless of new messages."
        ),
    )
    async def send_message(  # pyright: ignore[reportUnusedFunction]
        ctx: ToolContext, channel_id: str, text: str, force: bool
    ) -> dict[str, Any]:
        """Post a message with optimistic concurrency control."""
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        _reject_if_terminated(session=session, tool_name="send_message")
        async with session.track_active_call():
            agent_id = session.agent_id
            if not runtime.channel_router.validate_membership(
                agent_id=agent_id,
                channel_id=channel_id,
            ):
                raise ValueError(f"You are not a member of channel '{channel_id}'")

            rejection_reason = runtime.scenario.validate_outgoing_message(
                agent_id=agent_id,
                channel_id=channel_id,
            )
            if rejection_reason is not None:
                return SendMessageResult(
                    status="rejected",
                    detail=rejection_reason,
                    new_messages=[],
                    token_count=0,
                    current_round=runtime.current_round,
                    message_id=None,
                ).model_dump()

            # Count tokens before acquiring the lock to avoid holding the lock
            # during a potentially slow external API call.
            token_count = await runtime.count_tokens(agent_id=agent_id, text=text)

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
                            round=msg.round_number,
                            sender=msg.sender_display_name,
                            text=msg.text,
                            elapsed_seconds=elapsed_seconds_since_start(
                                when=msg.timestamp,
                                start=runtime.simulation_start_time,
                            ),
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
                        token_count=0,
                        current_round=runtime.current_round,
                        message_id=None,
                    ).model_dump()

                transformed_text = runtime.scenario.transform_outgoing_message(
                    agent_id=agent_id,
                    channel_id=channel_id,
                    text=text,
                )
                message = SimulationMessage(
                    message_id=str(uuid4()),
                    channel_id=channel_id,
                    sender_agent_id=agent_id,
                    sender_display_name=runtime.scenario.get_agent_display_name_at_round(
                        agent_id=agent_id,
                        round_number=runtime.current_round,
                    ),
                    text=transformed_text,
                    timestamp=datetime.now(tz=UTC),
                    round_number=runtime.current_round,
                )
                runtime.channel_router.append_message(message=message)
                await runtime.event_logger.log(
                    event=MessageSent(
                        message=message,
                        round_number=runtime.current_round,
                        token_count=token_count,
                    )
                )

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

            runtime.notify_world_of_message(
                agent_id=agent_id,
                channel_id=channel_id,
                text=text,
                token_count=token_count,
            )
            logger.info("Agent %s sent %d tokens to channel %s", agent_id, token_count, channel_id)
            return SendMessageResult(
                status="sent",
                detail=f"Message sent to channel '{channel_id}'",
                new_messages=[],
                token_count=token_count,
                current_round=runtime.current_round,
                message_id=message.message_id,
            ).model_dump()

    @mcp.tool(
        name="list_channels",
        description="See which channels you have access to.",
    )
    async def list_channels(
        ctx: ToolContext,
    ) -> list[dict[str, str]]:  # pyright: ignore[reportUnusedFunction]
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
    async def get_channel_members(
        ctx: ToolContext, channel_id: str
    ) -> list[dict[str, str]]:  # pyright: ignore[reportUnusedFunction]
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
                "display_name": runtime.scenario.get_agent_display_name_at_round(
                    agent_id=mid,
                    round_number=runtime.current_round,
                ),
            }
            for mid in member_ids
        ]

    # Register scenario-specific tools with an authorization guard.
    # Each executor is wrapped so that only agents whose allowlist
    # includes the tool name can invoke it.
    for scenario_tool in runtime.scenario.get_mcp_tools():
        guarded = _build_guarded_executor(
            tool_name=scenario_tool.name,
            original_executor=scenario_tool.executor,
            runtime=runtime,
        )
        mcp.tool(
            name=scenario_tool.name,
            description=scenario_tool.description,
        )(guarded)
        logger.info("Registered scenario MCP tool: %s", scenario_tool.name)
