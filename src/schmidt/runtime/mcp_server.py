"""Starts the FastMCP server over Streamable HTTP transport.

Creates a FastMCP instance, registers simulation tools, and runs the
HTTP server as an asyncio-compatible coroutine.
"""

import logging

from mcp.server.fastmcp import FastMCP

from schmidt.runtime.mcp_tools import register_tools
from schmidt.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)


async def start_mcp_server(runtime: SimulationRuntime, port: int) -> None:
    """Create the FastMCP server, register tools, and serve over HTTP.

    Blocks until the server is shut down. Intended to be run as an asyncio task
    alongside the game clock and agent runners.
    """
    mcp = FastMCP(
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
