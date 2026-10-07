"""MCP tool definitions for the simulation runtime.

Registers tools on an MCP server that agents call to interact with the
shared simulation world. Agent identity is resolved from the MCP connection
context (HTTP query parameter), not from tool arguments. Scenario-specific
tools are wrapped with an authorization guard that checks the per-agent
allowlist in ``SimulationRuntime`` before dispatching.
"""

# The tool handlers below are registered via ``@mcp.tool(...)``;
# pyright can't see the framework's runtime use of them.
# pyright: reportUnusedFunction=false

import asyncio
import functools
import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from glossogen.elapsed_time import elapsed_seconds_since_start
from glossogen.mcp_tool_rejection import surface_value_errors
from glossogen.models.interaction_protocol import (
    InteractionProtocol,
    is_workspace_action_protocol,
)
from glossogen.models.mcp_responses import (
    ChannelMessage,
    ReadChannelResult,
    SendMessageResult,
    SendResult,
)
from glossogen.runners.communication_protocol import (
    FINISH_TOOL_NAME,
    SEND_TOOL_NAME,
    WAIT_FOR_MESSAGE_TOOL_NAME,
)
from glossogen.runtime.activity_notification import (
    ActivityNotification,
    NewMessagesNotification,
    NoActivityNotification,
)
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.scenario_mcp_tool import (
    ToolContext,
    calling_agent_id,
    resolve_agent_id,
)
from glossogen.runtime.simulation_state import SimulationRuntime

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

WORKSPACE_ACTION_NOTIFICATION_TIMEOUT_SECONDS = 5.0
"""How long a ``workspace_action`` agent's ``read_notifications`` waits before ``no_activity``.

Such an agent reads its task card once and then learns of messages from tool
results, so a later poll has nothing to wait for and must not stall its turn.
"""


def protocol_tool_names(interaction_protocol: InteractionProtocol) -> frozenset[str]:
    """Tools the runtime registers for agents on ``interaction_protocol``.

    These are neither base tools (every agent has those) nor scenario tools (the
    scenario declares those). An agent is offered the ones its role's
    ``tool_names`` lists, so a scenario withholds ``send`` and
    ``wait_for_message`` from agents that cannot message.
    """
    if is_workspace_action_protocol(interaction_protocol):
        return frozenset({SEND_TOOL_NAME, WAIT_FOR_MESSAGE_TOOL_NAME, FINISH_TOOL_NAME})
    return frozenset()


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
    instructions seen on a channel before the current round are stale,
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
    (e.g. ``http://localhost:8001/mcp?agent_id=engineer``). A transport with no
    HTTP request falls back to ``calling_agent_id``, which an in-process
    dispatch sets because the tool runs in the calling agent's own task.
    """
    request = ctx.request_context.request
    if request is None:
        bound = calling_agent_id.get()
        if bound is None:
            raise ToolError(
                "Cannot resolve agent identity: no HTTP request in MCP context and no "
                "calling agent bound. Set calling_agent_id, or use Streamable HTTP with "
                "an ?agent_id= query parameter."
            )
        return runtime.resolve_session(agent_id=bound)
    agent_id = request.query_params.get("agent_id")
    if agent_id is None:
        raise ToolError(
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
    boundary. ``read_notifications`` is exempt, because the dying runner must
    still be able to read its Done signal to exit cleanly.
    """
    if session.terminated:
        raise ToolError(
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
    ``ToolError``, whose message the server hands to the agent.

    The wrapper preserves the original function's signature so that
    the server can introspect parameter names and types for the tool schema.
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
            raise ToolError(f"Agent '{agent_id}' is not authorized to call tool '{tool_name}'")
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

    # Preserve the original signature so the server generates the correct
    # JSON schema for the tool's parameters.
    _guarded.__signature__ = inspect.signature(original_executor)  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
    return _guarded


def register_tools(mcp: MCPServer, runtime: SimulationRuntime) -> None:
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
        note: str | None = None,
    ) -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        """Block until there is activity for the agent, then return it.

        ``note`` is accepted and ignored. Qwen models attach an invented argument
        to a call of a tool that takes none, which fails validation; with one
        optional field to fill they fill that instead.

        For NewMessagesNotifications, filters out channels the agent has
        already read (last_seen >= actual count). If all channels in a
        notification are stale, the notification is discarded and the agent
        continues waiting for the next one.

        Returns a no-activity response after 120 seconds of silence so agents
        are not stuck waiting indefinitely, or after
        ``WORKSPACE_ACTION_NOTIFICATION_TIMEOUT_SECONDS`` for a
        ``workspace_action`` agent.

        Rejects parallel invocation: when the LLM dispatches
        ``read_notifications`` alongside other tool calls in the same turn,
        the parallel call would block the cycle from reacting to the
        sibling tools' results until either a new notification arrives or
        the 120s timeout fires. To force the LLM to sequence calls, this
        function returns ``no_activity`` immediately when another
        non-blocking call is in flight, or another ``read_notifications``
        is already pending, for the same agent.
        """
        _ = note
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
        timeout_seconds = 120.0
        config = runtime.get_agent_config(agent_id=session.agent_id)
        if is_workspace_action_protocol(config.interaction_protocol):
            timeout_seconds = WORKSPACE_ACTION_NOTIFICATION_TIMEOUT_SECONDS
        while True:
            try:
                notification = await asyncio.wait_for(
                    session.wait_for_notification(),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                session.is_idle = False
                logger.info(
                    "Agent %s read_notifications timed out after %.1fs, returning no_activity",
                    session.agent_id,
                    timeout_seconds,
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
                raise ToolError(f"You are not a member of channel '{channel_id}'")
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
                raise ToolError(f"You are not a member of channel '{channel_id}'")
            protocol = runtime.get_agent_config(agent_id=agent_id).interaction_protocol
            if is_workspace_action_protocol(protocol):
                raise ToolError(f"Use {SEND_TOOL_NAME}(text) in this protocol.")

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

                published = await runtime.record_public_message(
                    agent_id=agent_id,
                    channel_id=channel_id,
                    text=text,
                    token_count=token_count,
                    recipient_agent_ids=None,
                    reply_to=None,
                )
                message = published.message

                session.record_channel_read(
                    channel_id=channel_id,
                    message_count=actual_count + 1,
                )

            await runtime.notify_world_of_message(
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

    async def send(
        ctx: ToolContext,
        text: str,
        to: list[str] | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Store one public message for a ``workspace_action`` agent and return its receipt.

        There is no conflict check: the message is appended, charged to the
        round budget, and announced. The receipt carries the scenario's current
        observation and the sender's unread public messages, drained through the
        scenario's delivery path, so the send itself refreshes the agent's view.
        """
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        _reject_if_terminated(session=session, tool_name=SEND_TOOL_NAME)
        async with session.track_active_call():
            agent_id = session.agent_id
            config = runtime.get_agent_config(agent_id=agent_id)
            if not is_workspace_action_protocol(config.interaction_protocol):
                raise ToolError(
                    f"'{SEND_TOOL_NAME}' is only available under workspace_action; "
                    "use send_message."
                )
            channel_ids = runtime.channel_router.get_agent_channel_ids(agent_id=agent_id)
            if len(channel_ids) != 1:
                raise ToolError(
                    f"'{SEND_TOOL_NAME}' needs exactly one public channel; "
                    f"agent '{agent_id}' has {len(channel_ids)}."
                )
            channel_id = channel_ids[0]
            members = runtime.channel_router.get_channel_member_ids(channel_id=channel_id)
            if to is not None:
                if not to or any(member not in members or member == agent_id for member in to):
                    raise ToolError(
                        "to must contain one or more teammate agent IDs; omit to to broadcast"
                    )
                to = list(dict.fromkeys(to))
            if reply_to is not None:
                visible = runtime.channel_router.get_visible_history(channel_id, agent_id)
                if not any(
                    m.message_id == reply_to and m.round_number == runtime.current_round
                    for m in visible
                ):
                    raise ToolError("reply_to must identify a message visible to you in this round")
            rejection_reason = runtime.scenario.validate_outgoing_message(
                agent_id=agent_id,
                channel_id=channel_id,
            )
            if rejection_reason is not None:
                return SendResult(
                    status="rejected",
                    detail=rejection_reason,
                    token_count=0,
                    current_round=runtime.current_round,
                    message_id=None,
                    context=None,
                ).model_dump()
            token_count = await runtime.count_tokens(agent_id=agent_id, text=text)
            async with runtime.get_channel_lock(channel_id=channel_id):
                published = await runtime.record_public_message(
                    agent_id=agent_id,
                    channel_id=channel_id,
                    text=text,
                    token_count=token_count,
                    recipient_agent_ids=to,
                    reply_to=reply_to,
                )
            await runtime.notify_world_of_message(
                agent_id=agent_id,
                channel_id=channel_id,
                text=text,
                token_count=token_count,
            )
            context = await runtime.scenario.deliver_send_context(
                agent_id=agent_id,
                channel_id=channel_id,
            )
            logger.info("Agent %s sent %d tokens to channel %s", agent_id, token_count, channel_id)
            return SendResult(
                status="sent",
                detail="Queued for recipients; this does not mean read or agreed.",
                token_count=token_count,
                current_round=runtime.current_round,
                message_id=published.message.message_id,
                context=context,
            ).model_dump()

    async def suspend_stub(ctx: ToolContext) -> str:
        """Answer a suspension call that reached the server instead of the runner.

        The runner intercepts ``wait_for_message`` and ``finish`` before any tool
        runs, so this executes only for a call issued from another client.
        """
        agent_id = _resolve_agent_from_context(ctx=ctx, runtime=runtime).agent_id
        raise ToolError(
            f"A suspension call for {agent_id} reached the workspace server. The runner "
            "suspends wait_for_message and finish before execution; call one by itself."
        )

    async def wait_for_message(ctx: ToolContext, timeout_s: float | None = None) -> str:
        """Schema for ``wait_for_message``; the runner intercepts the call."""
        _ = timeout_s
        return await suspend_stub(ctx=ctx)

    async def finish(ctx: ToolContext, note: str | None = None) -> str:
        """Schema for ``finish``; the runner intercepts the call."""
        _ = note
        return await suspend_stub(ctx=ctx)

    if any(
        is_workspace_action_protocol(config.interaction_protocol)
        for config in runtime.agent_configs()
    ):
        mcp.tool(
            name=WAIT_FOR_MESSAGE_TOOL_NAME,
            description=(
                "Free. End your turn and suspend until a message addressed to you or a "
                "broadcast from someone else arrives, or a lifecycle event. Optional "
                "timeout_s wakes you after that many seconds. Must be the only call."
            ),
        )(wait_for_message)
        mcp.tool(
            name=FINISH_TOOL_NAME,
            description=(
                "Declare you have finished this round and stop participating until the "
                "next round. This does not certify team success. Must be the only call."
            ),
        )(finish)
        mcp.tool(
            name=SEND_TOOL_NAME,
            description=(
                "Send to teammate IDs in to, or omit to to broadcast. Optional reply_to is a "
                "visible message ID. Queued does not mean read or agreed. Stored and charged at "
                "once; nothing is held back for new messages. The receipt includes your "
                "current workspace observation and any public messages you have not seen."
            ),
        )(send)

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
            raise ToolError(f"You are not a member of channel '{channel_id}'")
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
        )(surface_value_errors(tool_fn=guarded))
        logger.info("Registered scenario MCP tool: %s", scenario_tool.name)
