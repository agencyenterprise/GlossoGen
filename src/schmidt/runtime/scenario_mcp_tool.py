"""Model for scenario-specific MCP tools registered on the simulation runtime."""

from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple, TypeAlias

from mcp.server.fastmcp import Context

# Concrete Context type used by scenario tool executors.
ToolContext: TypeAlias = Context[Any, Any, Any]


def resolve_agent_id(ctx: ToolContext) -> str:
    """Extract agent_id from the MCP HTTP connection context.

    Agent identity is embedded in the Streamable HTTP connection URL as a
    query parameter (e.g. ``http://localhost:8001/mcp?agent_id=engineer``).
    """
    request = ctx.request_context.request
    if request is None:
        raise ValueError(
            "Cannot resolve agent identity: no HTTP request in MCP context. "
            "Agent identity requires Streamable HTTP transport with ?agent_id= query parameter."
        )
    agent_id: str | None = request.query_params.get("agent_id")
    if agent_id is None:
        raise ValueError(
            "Cannot resolve agent identity: missing ?agent_id= query parameter "
            f"on MCP connection URL. Request path: {request.url.path}"
        )
    return agent_id


class ScenarioMcpTool(NamedTuple):
    """A scenario-specific tool to be registered on the MCP server.

    The executor is an async callable registered directly with FastMCP.
    It may accept a ``ctx: ToolContext`` parameter to access agent identity
    via ``resolve_agent_id(ctx)``; FastMCP auto-injects the context and
    hides it from the LLM-facing tool schema.
    """

    name: str
    description: str
    executor: Callable[..., Awaitable[str]]
