"""`tools/list` is trimmed per agent when it goes through the MCP dispatcher.

This exists because the unit tests for this filter passed while the filter did
nothing. They call the decision functions directly, and those were correct; what
was wrong was the shape the middleware receives. mcp 2.0 hands middleware the
serialized JSON-RPC payload, a `dict` whose tools are dicts, not the
`ListToolsResult` the handler returned, so a type guard written against the model
skipped every request and every agent saw every tool.

So this drives a real `MCPServer` through a real client session. No socket and no
waiting: the client and server are joined by in-memory streams, so the exchange
is as deterministic as a function call.
"""

import logging

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult

from glossogen.runtime.mcp_server import per_agent_tool_filter
from glossogen.runtime.scenario_mcp_tool import calling_agent_id
from tests.fakes.in_memory_mcp_session import ask

MINE = "stabilize_veyru"
THEIRS = "read_stellar_reader"
BASE = "send_message"


class OneToolEach:
    """Authorizes exactly one scenario tool for one agent, and records questions."""

    def __init__(self, allowed: dict[str, str]) -> None:
        self._allowed = allowed
        self.asked: list[tuple[str, str]] = []

    def is_tool_allowed(self, agent_id: str, tool_name: str) -> bool:
        """Record the question, then answer it from the map."""
        self.asked.append((agent_id, tool_name))
        return self._allowed.get(agent_id) == tool_name

    def is_base_tool_hidden(self, agent_id: str, tool_name: str) -> bool:
        """Hide no base tool, as for an agent on the communication protocol."""
        _ = agent_id, tool_name
        return False


def build_server(authorizer: OneToolEach) -> MCPServer:
    """An MCP server carrying one base tool and two scenario tools."""
    server = MCPServer(
        name="filter-probe", middleware=[per_agent_tool_filter(authorizer=authorizer)]
    )
    server.tool(name=BASE, description="base")(lambda: "sent")
    server.tool(name=MINE, description="scenario")(lambda: "stabilized")
    server.tool(name=THEIRS, description="scenario")(lambda: "read")
    return server


async def list_tool_names(session: ClientSession) -> list[str]:
    """Return the tool names this session is shown."""
    listed = await session.list_tools()
    return sorted(tool.name for tool in listed.tools)


def tools_seen_by(server: MCPServer, agent_id: str) -> list[str]:
    """Ask for tools as ``agent_id``, the way an in-process agent's task does."""

    async def run() -> list[str]:
        """Set the identity for the duration of the exchange."""
        token = calling_agent_id.set(agent_id)
        try:
            return await ask(server, list_tool_names)
        finally:
            calling_agent_id.reset(token)

    return anyio.run(run)


def test_each_agent_is_shown_only_its_own_scenario_tool() -> None:
    """The leak this file was written for: an unauthorized tool staying visible.

    `stabilization_engineer` is authorized for nothing, so it sees the base
    communication tool and neither scenario tool.
    """
    authorizer = OneToolEach(allowed={"field_observer": MINE})
    server = build_server(authorizer)

    assert tools_seen_by(server, "field_observer") == sorted([BASE, MINE])
    assert tools_seen_by(server, "stabilization_engineer") == [BASE]


def test_the_allowlist_is_actually_consulted() -> None:
    """A filter that returns the right answer without asking is the failure mode.

    The regression satisfied every assertion about `visible_tools` while never
    reaching it, so this asserts the authorizer was questioned.
    """
    authorizer = OneToolEach(allowed={"field_observer": MINE})
    server = build_server(authorizer)

    tools_seen_by(server, "field_observer")

    assert ("field_observer", THEIRS) in authorizer.asked


def test_base_tools_are_never_hidden_even_with_nothing_authorized() -> None:
    """An agent that cannot see `send_message` cannot take part at all."""
    authorizer = OneToolEach(allowed={})
    server = build_server(authorizer)

    assert tools_seen_by(server, "field_observer") == [BASE]


def test_an_unidentified_caller_gets_everything_and_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nothing to attribute the call to means nothing to filter against.

    Every tool comes back, because refusing would end the run, and the warning is
    the only signal that the identity plumbing has broken. Asserting the log is
    the point: without it, this case reads exactly like the filter being broken,
    which is the bug this file exists for.
    """
    authorizer = OneToolEach(allowed={"field_observer": MINE})
    server = build_server(authorizer)

    with caplog.at_level(logging.WARNING, logger="glossogen.runtime.mcp_server"):
        seen = anyio.run(ask, server, list_tool_names)

    assert seen == sorted([BASE, MINE, THEIRS])
    assert "without an identifiable agent" in caplog.text
    assert authorizer.asked == [], "nothing should have been authorized against"


def test_other_methods_pass_through_untouched() -> None:
    """The middleware wraps every request, so a tool call must be unaffected."""
    authorizer = OneToolEach(allowed={"field_observer": MINE})
    server = build_server(authorizer)

    async def call_the_tool(session: ClientSession) -> CallToolResult:
        """Call the one tool this agent is authorized for."""
        return await session.call_tool(MINE, {})

    async def run() -> CallToolResult:
        """Call as the authorized agent."""
        token = calling_agent_id.set("field_observer")
        try:
            return await ask(server, call_the_tool)
        finally:
            calling_agent_id.reset(token)

    assert anyio.run(run).is_error is False
