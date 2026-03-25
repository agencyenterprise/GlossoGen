"""Model for scenario-specific MCP tools registered on the simulation runtime."""

from collections.abc import Awaitable, Callable
from typing import NamedTuple


class ScenarioMcpTool(NamedTuple):
    """A scenario-specific tool to be registered on the MCP server.

    The executor is an async callable that takes keyword arguments matching
    the tool's parameters and returns a string result.

    When ``requires_agent_id`` is True, the executor's first positional
    argument is ``agent_id: str``. The MCP registration layer injects the
    agent identity from the HTTP connection context and hides it from the
    LLM-facing tool schema. Stateless tools that do not need agent identity
    set ``requires_agent_id`` to False.
    """

    name: str
    description: str
    executor: Callable[..., Awaitable[str]]
    # When True, executor receives agent_id as first arg, injected from MCP context.
    requires_agent_id: bool
