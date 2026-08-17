"""Starts the MCP server over Streamable HTTP transport with per-agent tool filtering.

A ``tools/list`` answer is trimmed to the tools the asking agent may call. Base
communication tools are always visible; scenario tools are checked against the
per-agent allowlist the runtime holds.

The trimming is middleware rather than a ``list_tools`` override, because the
agent's identity is on the per-request context and middleware is what gets handed
it. Hiding a tool is not what enforces the allowlist: ``mcp_tools`` checks it
again when a tool is actually called, so an agent that guesses a name it was
never shown is still refused.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from mcp.server.context import ServerMiddleware, ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.types import ListToolsResult
from mcp.types import Tool as MCPTool
from starlette.requests import Request

from glossogen.runtime.mcp_tools import BASE_TOOL_NAMES, register_tools
from glossogen.runtime.scenario_mcp_tool import calling_agent_id
from glossogen.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)


LIST_TOOLS_METHOD = "tools/list"


class ToolAuthorizer(Protocol):
    """The one thing the filter asks of the runtime.

    Narrower than ``SimulationRuntime`` so the decision can be exercised without
    standing up a simulation to ask it.
    """

    def is_tool_allowed(self, agent_id: str, tool_name: str) -> bool:
        """Return whether ``agent_id`` may call ``tool_name``."""
        ...


def requesting_agent_id(request: Request | None) -> str | None:
    """Return the agent behind this request, however it arrived.

    Over Streamable HTTP the identity is in the connection URL. In-process there
    is no request to read, and the call runs in the agent's own task, so the
    contextvar that task set is the identity.
    """
    if request is None:
        return calling_agent_id.get()
    return request.query_params.get("agent_id")


def visible_tools(tools: list[MCPTool], agent_id: str, authorizer: ToolAuthorizer) -> list[MCPTool]:
    """Return the subset of ``tools`` that ``agent_id`` is allowed to see."""
    visible: list[MCPTool] = []
    for tool in tools:
        if tool.name in BASE_TOOL_NAMES:
            visible.append(tool)
        elif authorizer.is_tool_allowed(agent_id=agent_id, tool_name=tool.name):
            visible.append(tool)
        else:
            logger.debug("Hiding tool %s from agent %s (not in allowlist)", tool.name, agent_id)
    return visible


def per_agent_tool_filter(authorizer: ToolAuthorizer) -> ServerMiddleware[Any]:
    """Build middleware that trims ``tools/list`` to what the asking agent may call."""

    async def filter_tools(
        ctx: ServerRequestContext[Any, Any],
        call_next: Callable[[ServerRequestContext[Any, Any]], Awaitable[Any]],
    ) -> Any:
        """Trim a ``tools/list`` answer, and pass every other method through."""
        result = await call_next(ctx)
        if ctx.method != LIST_TOOLS_METHOD or not isinstance(result, ListToolsResult):
            return result

        agent_id = requesting_agent_id(request=ctx.request)
        if agent_id is None:
            logger.warning("tools/list called without an identifiable agent, returning all tools")
            return result

        return result.model_copy(
            update={
                "tools": visible_tools(tools=result.tools, agent_id=agent_id, authorizer=authorizer)
            }
        )

    return filter_tools


def build_mcp_server(runtime: SimulationRuntime) -> MCPServer:
    """Create the MCP server with every tool registered and per-agent filtering on.

    Split from serving so a caller can mount the ASGI app directly instead of
    binding a socket. Where it listens is stated at serve time rather than here,
    so an in-process caller states nothing.
    """
    mcp = MCPServer(name="comms", middleware=[per_agent_tool_filter(authorizer=runtime)])
    register_tools(mcp=mcp, runtime=runtime)
    return mcp


async def start_mcp_server(runtime: SimulationRuntime, port: int) -> None:
    """Create the filtering MCP server, register tools, and serve over HTTP.

    Blocks until the server is shut down. Intended to be run as an asyncio task
    alongside the game clock and agent runners.
    """
    mcp = build_mcp_server(runtime=runtime)
    logger.info("Starting MCP server on port %d", port)
    try:
        await mcp.run_streamable_http_async(host="127.0.0.1", port=port)
    except Exception:
        logger.exception("MCP server exited unexpectedly on port %d", port)
        raise
