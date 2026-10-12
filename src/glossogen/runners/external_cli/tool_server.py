"""One seat's tools, served over MCP on a loopback port for an agent CLI to connect to.

The server offers the seat the same tools a pydantic-ai seat gets, through the
same executors and error handling (:mod:`glossogen.runners.agent_tools`), and
``read_notifications`` parks through the same wait
(:mod:`glossogen.runners.read_notifications_tool`). Each call is logged as
``tool_call_invoked`` and ``tool_result_received`` here, since the platform
never sees the model response that issued it. A ``read_notifications`` call
issued beside other calls cannot be told apart from one issued alone, so none
is refused.

The endpoint is protected by a bearer token the runner generates for the seat.
It binds to loopback only, and answers each request with a JSON response rather
than an SSE stream, so a parked ``read_notifications`` call is one HTTP request
held open until its wake.
"""

import asyncio
import inspect
import logging
import secrets
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Literal, NamedTuple

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from glossogen.models.event import ToolCallInvoked, ToolResultReceived
from glossogen.port_allocator import find_free_port
from glossogen.runners.agent_tools import (
    ToolOutcome,
    ToolSpec,
    execute_tool_spec,
    offered_tool_specs,
    serialize_tool_result,
    with_schema_of,
)
from glossogen.runners.read_notifications_tool import RunTermination, park_and_render
from glossogen.runtime.read_notifications_schema import (
    READ_NOTIFICATIONS_TOOL_NAME,
    ReadNotificationsArguments,
)
from glossogen.runtime.simulation_state import SimulationRuntime

logger = logging.getLogger(__name__)

TOOL_SERVER_NAME = "glossogen"
MCP_PATH = "/mcp"
STARTUP_POLL_SECONDS = 0.01


class AgentToolEndpoint(NamedTuple):
    """Where a seat's tools are served, and the token that opens them."""

    url: str
    token: str


class AgentToolServer:
    """Serves one seat's tools over MCP until stopped."""

    def __init__(
        self, runtime: SimulationRuntime, agent_id: str, termination: RunTermination
    ) -> None:
        self._runtime = runtime
        self._agent_id = agent_id
        self._termination = termination
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> AgentToolEndpoint:
        """Bind a loopback port and serve until ``stop``."""
        token = secrets.token_urlsafe(32)
        port = find_free_port()
        mcp = MCPServer(TOOL_SERVER_NAME, instructions=None)
        for spec in offered_tool_specs(runtime=self._runtime, agent_id=self._agent_id):
            mcp.add_tool(
                self._logged(name=spec.name, run=self._spec_call(spec=spec)),
                name=spec.name,
                description=spec.description,
            )
        mcp.add_tool(
            self._logged(name=READ_NOTIFICATIONS_TOOL_NAME, run=self._read_notifications),
            name=READ_NOTIFICATIONS_TOOL_NAME,
            description=self._runtime.scenario.read_notifications_description(),
        )
        app = mcp.streamable_http_app(
            streamable_http_path=MCP_PATH,
            json_response=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
            host="127.0.0.1",
        )
        config = uvicorn.Config(
            app=_BearerTokenGate(app=app, token=token),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config=config)
        self._task = asyncio.create_task(self._server.serve(), name=f"tools-{self._agent_id}")
        while not self._server.started:
            if self._task.done():
                self._task.result()
                raise RuntimeError(f"the tool server for {self._agent_id} stopped before binding")
            await asyncio.sleep(STARTUP_POLL_SECONDS)
        logger.info("Serving %s's tools at http://127.0.0.1:%d%s", self._agent_id, port, MCP_PATH)
        return AgentToolEndpoint(url=f"http://127.0.0.1:{port}{MCP_PATH}", token=token)

    async def stop(self) -> None:
        """Stop serving; a call still parked returns to a closed connection."""
        if self._server is None or self._task is None:
            return
        self._server.should_exit = True
        await self._task
        self._server = None
        self._task = None

    def _spec_call(self, spec: ToolSpec) -> Callable[..., Awaitable[ToolOutcome]]:
        """A function with ``spec``'s parameters that runs it as this seat."""

        async def call(**arguments: Any) -> ToolOutcome:
            return await execute_tool_spec(
                spec=spec, runtime=self._runtime, agent_id=self._agent_id, arguments=arguments
            )

        return with_schema_of(function=call, spec=spec)

    async def _read_notifications(
        self,
        wait_for: Literal["any", "message", "next_round"] = "any",
        timeout_s: float | None = None,
    ) -> ToolOutcome:
        """Park until something happens for this seat. The parameters mirror the tool's schema."""
        arguments = ReadNotificationsArguments(wait_for=wait_for, timeout_s=timeout_s)
        rendered = await park_and_render(
            runtime=self._runtime,
            agent_id=self._agent_id,
            arguments=arguments,
            termination=self._termination,
        )
        return ToolOutcome(content=rendered, is_error=False)

    def _logged(
        self, name: str, run: Callable[..., Awaitable[ToolOutcome]]
    ) -> Callable[..., Awaitable[str]]:
        """``run``, with the call and its result logged, and an error raised as the tool's."""

        async def logged(**arguments: Any) -> str:
            call_id = uuid.uuid4().hex
            await self._runtime.event_logger.log(
                event=ToolCallInvoked(
                    agent_id=self._agent_id,
                    round_number=self._runtime.current_round,
                    call_id=call_id,
                    tool_name=name,
                    arguments=dict(arguments),
                )
            )
            outcome = await run(**arguments)
            result = serialize_tool_result(content=outcome.content)
            await self._runtime.event_logger.log(
                event=ToolResultReceived(
                    agent_id=self._agent_id,
                    round_number=self._runtime.current_round,
                    tool_name=name,
                    call_id=call_id,
                    arguments=dict(arguments),
                    result=result,
                )
            )
            if outcome.is_error:
                raise ToolError(result)
            return result

        logged.__signature__ = inspect.signature(run).replace(return_annotation=str)  # type: ignore[attr-defined]  # pyright: ignore[reportFunctionMemberAccess]
        logged.__annotations__ = {**run.__annotations__, "return": str}
        logged.__name__ = name
        return logged


class _BearerTokenGate:
    """An ASGI wrapper answering 401 to any HTTP request without the seat's token."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not self._authorized(scope=scope):
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"text/plain")],
                }
            )
            await send({"type": "http.response.body", "body": b"unauthorized"})
            return
        await self._app(scope, receive, send)

    def _authorized(self, scope: Scope) -> bool:
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                return secrets.compare_digest(value, self._expected)
        return False
