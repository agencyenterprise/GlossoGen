"""How a scenario exposes its own tools to agents.

A scenario returns one ``ScenarioMcpTool`` per tool from ``get_mcp_tools``, and
the runtime registers each with FastMCP alongside the base communication tools.

An executor that needs to know who called it takes a ``ctx: ToolContext`` first
argument and passes it to ``resolve_agent_id``, which reads the id off the MCP
connection URL. FastMCP fills the context in and keeps it out of the schema the
model sees, so identity is a property of the connection rather than something
the model supplies per call.
"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any, NamedTuple, TypeAlias

from mcp.server.fastmcp import Context

# Concrete Context type used by scenario tool executors.
ToolContext: TypeAlias = Context[Any, Any, Any]


calling_agent_id: ContextVar[str | None] = ContextVar("calling_agent_id", default=None)
"""The agent whose task is currently calling a tool.

Set by a runner around its own MCP work. Over Streamable HTTP identity comes
from the connection URL and this stays unset; over an in-process transport the
tool executes in the calling agent's own task, so the variable it set is the
identity.
"""


def resolve_agent_id(ctx: ToolContext) -> str:
    """Return the agent whose call this is.

    Identity comes from the Streamable HTTP connection URL as a query parameter
    (e.g. ``http://localhost:8001/mcp?agent_id=engineer``). A transport with no
    HTTP request falls back to the calling task's ``calling_agent_id``.
    """
    request = ctx.request_context.request
    if request is None:
        bound = calling_agent_id.get()
        if bound is not None:
            return bound
        raise ValueError(
            "Cannot resolve agent identity: no HTTP request in MCP context and no "
            "calling agent bound. Set calling_agent_id, or use Streamable HTTP with "
            "an ?agent_id= query parameter."
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
