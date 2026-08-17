"""Each agent's `tools/list` is trimmed, asked the way a real run asks it.

Every other test of the simulation MCP server mounts it in-process, where an
agent's identity comes from a contextvar. A real run does not: it serves over
Streamable HTTP and each agent connects on its own URL, so identity arrives as a
query parameter and the filter reads a request object. That path had no test, and
it is the one every paid run uses.

The app is driven through `httpx`'s ASGI transport rather than a socket, so there
is no port to bind, no readiness to wait on, and nothing to race. The HTTP
semantics that matter here are all present: the host header the transport
security checks, the query string the identity comes from, and the session
handshake.
"""

import json
from typing import Any

import anyio
import httpx
from starlette.applications import Starlette

from glossogen.runtime.mcp_server import FilteringFastMCP

BASE_TOOL = "send_message"
OBSERVER_TOOL = "stabilize_veyru"
ENGINEER_TOOL = "read_stellar_reader"

OBSERVER = "field_observer"
ENGINEER = "stabilization_engineer"

# The default transport security allows `127.0.0.1:*`, which is what a run
# serves on, so the client has to address the app the same way.
BASE_URL = "http://127.0.0.1:8000"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


class AllowlistByAgent:
    """Answers `is_tool_allowed` from a map, and records what it was asked."""

    def __init__(self, allowed: dict[str, str]) -> None:
        self._allowed = allowed
        self.asked: list[tuple[str, str]] = []

    def is_tool_allowed(self, agent_id: str, tool_name: str) -> bool:
        """Record the question, then answer it."""
        self.asked.append((agent_id, tool_name))
        return self._allowed.get(agent_id) == tool_name


def build_app(authorizer: AllowlistByAgent) -> Starlette:
    """Build the simulation MCP server's ASGI app with one tool per agent."""
    server = FilteringFastMCP(runtime=authorizer, name="comms", host="127.0.0.1", port=0)
    for name in (BASE_TOOL, OBSERVER_TOOL, ENGINEER_TOOL):
        server.tool(name=name, description=name)(lambda: "ok")
    return server.streamable_http_app()


def sse_result(response: httpx.Response) -> dict[str, Any]:
    """Return the JSON-RPC result carried by a Streamable HTTP response.

    Answers arrive as one server-sent event, so the payload is the `data:` line
    rather than the body.
    """
    for line in response.text.splitlines():
        if line.startswith("data:"):
            message: dict[str, Any] = json.loads(line.removeprefix("data:").strip())
            return message["result"]
    raise AssertionError(f"no server-sent event in {response.text!r}")


async def tools_seen_by(client: httpx.AsyncClient, agent_id: str) -> list[str]:
    """Complete the handshake as ``agent_id`` and return the tools it is offered."""
    url = f"/mcp?agent_id={agent_id}"
    handshake = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "probe", "version": "1"},
        },
    }
    opened = await client.post(url, headers=MCP_HEADERS, json=handshake)
    assert opened.status_code == 200, opened.text
    session = {**MCP_HEADERS, "mcp-session-id": opened.headers["mcp-session-id"]}

    await client.post(
        url, headers=session, json={"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    listed = await client.post(
        url, headers=session, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )
    assert listed.status_code == 200, listed.text

    return sorted(tool["name"] for tool in sse_result(listed)["tools"])


def ask_over_http(authorizer: AllowlistByAgent, agent_ids: list[str]) -> dict[str, list[str]]:
    """Return what each agent is shown, over one run of the app's lifespan.

    One lifespan for all of them: the session manager refuses to start twice, and
    a run serves every agent from a single app.
    """
    app = build_app(authorizer)

    async def run() -> dict[str, list[str]]:
        """Drive the app without binding a socket."""
        seen: dict[str, list[str]] = {}
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
                for agent_id in agent_ids:
                    seen[agent_id] = await tools_seen_by(client=client, agent_id=agent_id)
        return seen

    return anyio.run(run)


def test_each_agent_is_offered_only_its_own_scenario_tool() -> None:
    """Two agents, one app, one request each: the split that makes a role a role.

    This is the assertion that would have caught a filter which stopped
    filtering. Every in-process test passes in that case, because they exercise
    the decision function rather than the request.
    """
    authorizer = AllowlistByAgent(allowed={OBSERVER: OBSERVER_TOOL, ENGINEER: ENGINEER_TOOL})

    seen = ask_over_http(authorizer=authorizer, agent_ids=[OBSERVER, ENGINEER])

    assert seen[OBSERVER] == sorted([BASE_TOOL, OBSERVER_TOOL])
    assert seen[ENGINEER] == sorted([BASE_TOOL, ENGINEER_TOOL])


def test_an_agent_authorized_for_nothing_still_gets_the_communication_tools() -> None:
    """Authorized for no scenario tool, and still able to talk.

    Base tools are exempt from the allowlist rather than granted by it. The same
    request also proves the scenario tools are withheld, which is the leak.
    """
    authorizer = AllowlistByAgent(allowed={})

    seen = ask_over_http(authorizer=authorizer, agent_ids=[ENGINEER])

    assert seen[ENGINEER] == [BASE_TOOL]


def test_the_allowlist_is_consulted_for_the_agent_named_in_the_url() -> None:
    """The identity has to come off the query string, not from anywhere else.

    In-process the filter reads a contextvar, and over HTTP there is no such
    task, so a filter that only knew the contextvar would attribute every
    request to nobody and answer with everything.
    """
    authorizer = AllowlistByAgent(allowed={OBSERVER: OBSERVER_TOOL})

    ask_over_http(authorizer=authorizer, agent_ids=[OBSERVER])

    assert (OBSERVER, ENGINEER_TOOL) in authorizer.asked
    assert all(asked_agent == OBSERVER for asked_agent, _ in authorizer.asked)
