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
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from glossogen.elapsed_time import elapsed_seconds_since_start
from glossogen.mcp_tool_rejection import surface_value_errors
from glossogen.models.mcp_responses import ChannelMessage, ReadChannelResult
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.scenario_mcp_tool import (
    ToolContext,
    calling_agent_id,
    resolve_agent_id,
)
from glossogen.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)

NON_BLOCKING_TOOL_TIMEOUT_SECONDS = 120.0
"""Hard cap on any single non-blocking tool body (scenario tools, send_message,
read_channel). Sits well under the MCP client's ~300s request timeout so a
stalled call (e.g. a judge HTTP request that hangs) is cancelled server-side,
releasing the agent's in-flight slot and returning a clean error to the agent
instead of wedging it for the rest of the round."""

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
authorization guard. ``read_notifications`` is executed by the agent runner,
not registered here; see ``glossogen.runners.read_notifications_tool``.
"""


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


def _reject_if_hidden(runtime: SimulationRuntime, session: AgentSession, tool_name: str) -> None:
    """Raise if the scenario withholds the base tool ``tool_name`` from the caller."""
    if runtime.is_base_tool_hidden(agent_id=session.agent_id, tool_name=tool_name):
        raise ToolError(f"Tool '{tool_name}' is not available to you.")


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


def _scenario_send_message(runtime: SimulationRuntime) -> Callable[..., Awaitable[dict[str, Any]]]:
    """Return the ``send_message`` tool function, delegating to the scenario's executor.

    The tool's parameters are the executor's, without ``agent_id``, which comes
    from the calling connection; so a scenario whose executor takes other
    parameters changes the schema agents are offered.
    """
    method = runtime.scenario.send_message_executor()
    signature = inspect.signature(method)
    parameters = [
        parameter for name, parameter in signature.parameters.items() if name != "agent_id"
    ]

    async def send_message(ctx: ToolContext, **arguments: Any) -> dict[str, Any]:
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        _reject_if_terminated(session=session, tool_name="send_message")
        _reject_if_hidden(runtime=runtime, session=session, tool_name="send_message")
        async with session.track_active_call():
            result = await method(agent_id=session.agent_id, **arguments)
        return result.model_dump()

    context_parameter = inspect.Parameter(
        "ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=ToolContext
    )
    send_message.__signature__ = signature.replace(  # type: ignore[attr-defined]  # pyright: ignore[reportFunctionMemberAccess]
        parameters=[context_parameter, *parameters],
        return_annotation=dict[str, Any],
    )
    return send_message


def register_tools(mcp: MCPServer, runtime: SimulationRuntime) -> None:
    """Register all simulation MCP tools on the given FastMCP server.

    Registers the base communication tools other than ``read_notifications``,
    which the agent runner executes, plus any scenario-specific tools returned
    by ``scenario.get_mcp_tools()``.
    """

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
        _reject_if_hidden(runtime=runtime, session=session, tool_name="read_channel")
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

    mcp.tool(
        name="send_message",
        description=runtime.scenario.send_message_description(),
    )(surface_value_errors(tool_fn=_scenario_send_message(runtime=runtime)))

    @mcp.tool(
        name="list_channels",
        description="See which channels you have access to.",
    )
    async def list_channels(
        ctx: ToolContext,
    ) -> list[dict[str, str]]:  # pyright: ignore[reportUnusedFunction]
        """Return the channels the agent belongs to with display names."""
        session = _resolve_agent_from_context(ctx=ctx, runtime=runtime)
        _reject_if_hidden(runtime=runtime, session=session, tool_name="list_channels")
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
        _reject_if_hidden(runtime=runtime, session=session, tool_name="get_channel_members")
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
