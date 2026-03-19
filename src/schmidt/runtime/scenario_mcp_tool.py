"""Model for scenario-specific MCP tools registered on the simulation runtime."""

from collections.abc import Awaitable, Callable
from typing import NamedTuple


class ScenarioMcpTool(NamedTuple):
    """A scenario-specific tool to be registered on the MCP server.

    The executor is an async callable that takes keyword arguments matching
    the tool's parameters and returns a string result. It does NOT receive
    agent context — scenario tools are stateless functions.
    """

    name: str
    description: str
    executor: Callable[..., Awaitable[str]]
