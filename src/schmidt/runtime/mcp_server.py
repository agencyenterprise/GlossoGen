"""Starts the MCP server over Streamable HTTP transport with per-agent tool filtering.

Creates a ``FilteringFastMCP`` instance that extends FastMCP to return only
the tools each agent is authorized to see. Base communication tools are
always visible; scenario-specific tools are filtered against the per-agent
allowlist stored in ``SimulationRuntime``.
"""

import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.lowlevel.server import request_ctx
from mcp.types import Tool as MCPTool

from schmidt.runtime.mcp_tools import BASE_TOOL_NAMES, register_tools
from schmidt.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)


class FilteringFastMCP(FastMCP):
    """FastMCP subclass that filters ``tools/list`` responses per agent.

    When a client calls ``tools/list``, this reads the ``agent_id`` from
    the HTTP query parameters (set by the MCP library's ``request_ctx``
    contextvar) and returns only the tools that agent is allowed to see.
    Base communication tools are always included; scenario tools are
    filtered against ``SimulationRuntime.is_tool_allowed()``.
    """

    def __init__(self, runtime: SimulationRuntime, name: str, host: str, port: int) -> None:
        super().__init__(name=name, host=host, port=port)
        self._runtime = runtime

    async def list_tools(self) -> list[MCPTool]:
        """Return only the tools the requesting agent is authorized to see."""
        all_tools = await super().list_tools()

        ctx = request_ctx.get()
        request = ctx.request
        if request is None:
            logger.warning("list_tools called without HTTP request context, returning all tools")
            return all_tools

        agent_id = request.query_params.get("agent_id")
        if agent_id is None:
            logger.warning("list_tools called without agent_id query param, returning all tools")
            return all_tools

        filtered: list[MCPTool] = []
        for tool in all_tools:
            if tool.name in BASE_TOOL_NAMES:
                filtered.append(tool)
            elif self._runtime.is_tool_allowed(agent_id=agent_id, tool_name=tool.name):
                filtered.append(tool)
            else:
                logger.debug(
                    "Hiding tool %s from agent %s (not in allowlist)",
                    tool.name,
                    agent_id,
                )
        return filtered


async def start_mcp_server(runtime: SimulationRuntime, port: int) -> None:
    """Create the filtering MCP server, register tools, and serve over HTTP.

    Blocks until the server is shut down. Intended to be run as an asyncio task
    alongside the game clock and agent runners.
    """
    mcp = FilteringFastMCP(
        runtime=runtime,
        name="comms",
        host="127.0.0.1",
        port=port,
    )
    register_tools(mcp=mcp, runtime=runtime)
    logger.info("Starting MCP server on port %d", port)
    try:
        await mcp.run_streamable_http_async()
    except Exception:
        logger.exception("MCP server exited unexpectedly on port %d", port)
        raise
