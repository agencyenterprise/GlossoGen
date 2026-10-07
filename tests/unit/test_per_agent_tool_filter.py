"""Which tools a `tools/list` answer shows the agent that asked.

Hiding a tool is not what enforces the allowlist: `mcp_tools` checks it again
when a tool is called. What this protects is the agent's view of the world. A
scenario that splits work across roles does it by giving each role different
tools, so a filter that quietly stopped filtering would hand every agent every
other agent's actions, and nothing would fail.

Nothing here was covered while the filter was a `list_tools` override, because
that override needed a live request context to say anything at all.
"""

import logging
from typing import Any, cast

import pytest
from mcp.server.context import ServerRequestContext
from mcp.server.session import ServerSession
from mcp.types import Tool as MCPTool
from starlette.requests import Request

from glossogen.runtime.mcp_server import (
    LIST_TOOLS_METHOD,
    per_agent_tool_filter,
    requesting_agent_id,
    visible_tools,
)
from glossogen.runtime.mcp_tools import BASE_TOOL_NAMES
from glossogen.runtime.scenario_mcp_tool import calling_agent_id

BASE_TOOL = sorted(BASE_TOOL_NAMES)[0]
MINE = "stabilize_veyru"
THEIRS = "read_stellar_reader"


class AllowList:
    """A runtime stand-in that authorizes one tool for one agent."""

    def __init__(self, agent_id: str, tool_name: str) -> None:
        self._agent_id = agent_id
        self._tool_name = tool_name

    def is_tool_allowed(self, agent_id: str, tool_name: str) -> bool:
        """Authorize only the one pair this was built with."""
        return agent_id == self._agent_id and tool_name == self._tool_name

    def is_base_tool_hidden(self, agent_id: str, tool_name: str) -> bool:
        """Hide no base tool, as for an agent on the communication protocol."""
        _ = agent_id, tool_name
        return False


def tool(name: str) -> MCPTool:
    """Build a tool as the server would advertise it."""
    return MCPTool(name=name, description=name, input_schema={"type": "object"})


def test_an_agent_sees_its_own_scenario_tool_and_not_another_agents() -> None:
    """The split that makes a role a role."""
    shown = visible_tools(
        tools=[tool(BASE_TOOL), tool(MINE), tool(THEIRS)],
        agent_id="observer",
        authorizer=AllowList(agent_id="observer", tool_name=MINE),
    )

    assert [entry.name for entry in shown] == [BASE_TOOL, MINE]


def test_communication_tools_are_never_hidden() -> None:
    """An agent that cannot see `send_message` cannot take part at all.

    They are exempt from the allowlist rather than granted by it, so a scenario
    that authorizes nothing still leaves its agents able to talk.
    """
    shown = visible_tools(
        tools=[tool(name) for name in sorted(BASE_TOOL_NAMES)],
        agent_id="observer",
        authorizer=AllowList(agent_id="nobody", tool_name="nothing"),
    )

    assert {entry.name for entry in shown} == BASE_TOOL_NAMES


def test_the_agent_is_read_from_the_connection_url_over_http() -> None:
    """Each agent connects on its own URL, which is where its identity is."""

    request = Request(scope={"type": "http", "query_string": b"agent_id=engineer", "headers": []})

    assert requesting_agent_id(request=request) == "engineer"


def test_the_agent_falls_back_to_the_calling_task_in_process() -> None:
    """In-process there is no request: the tool runs in the agent's own task.

    A run that mounts the server rather than binding a port has no URL to read
    an identity from, so the contextvar the agent's task set is the identity.
    """
    token = calling_agent_id.set("observer")
    try:
        assert requesting_agent_id(request=None) == "observer"
    finally:
        calling_agent_id.reset(token)


def test_no_identity_anywhere_is_reported_rather_than_guessed() -> None:
    """Neither a request nor a calling task means the caller cannot be named.

    The filter answers with every tool in that case, and logs. Guessing an agent
    here would hand one agent another's tools.
    """
    assert requesting_agent_id(request=None) is None


async def test_a_tools_list_result_of_an_unknown_shape_is_logged_as_an_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A result the filter cannot read is passed through, and said so loudly.

    The filter is handed whatever the MCP library serializes, and that shape
    changed once already between major versions. When it changes again the
    filter cannot trim the list, so every agent sees every tool; the ERROR is
    the only sign of it.
    """
    unreadable = ("not", "a", "tool", "list")

    async def answer(_ctx: ServerRequestContext[Any, Any]) -> Any:
        """Stand in for the dispatcher, answering with a shape nobody expects."""
        return unreadable

    ctx: ServerRequestContext[Any, Any] = ServerRequestContext(
        session=cast(ServerSession, object()),
        lifespan_context=None,
        protocol_version="2025-06-18",
        method=LIST_TOOLS_METHOD,
    )
    token = calling_agent_id.set("observer")
    try:
        with caplog.at_level(logging.ERROR, logger="glossogen.runtime.mcp_server"):
            result = await per_agent_tool_filter(
                authorizer=AllowList(agent_id="observer", tool_name=MINE)
            )(ctx=ctx, call_next=answer)
    finally:
        calling_agent_id.reset(token)

    assert result is unreadable
    assert any("every agent is seeing every tool" in r.getMessage() for r in caplog.records)
