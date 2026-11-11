"""Passes a tool's deliberate rejection to the MCP client as text it can read.

The MCP server reports a ``ToolError`` to the caller with its message, and treats
any other exception as a crash: the caller is told only ``Error executing tool
<name>`` and the text stays in the server log. Code behind a tool that is not
written against MCP, such as the run browser's lookups, rejects a call by
raising ``ValueError``. Wrapping the tool where it is registered turns that one
type into a ``ToolError``, so the client reads the reason instead of a generic
failure.
"""

import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from mcp.server.mcpserver.exceptions import ToolError

P = ParamSpec("P")
R = TypeVar("R")


def surface_value_errors(tool_fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Wrap ``tool_fn`` so a ``ValueError`` it raises reaches the caller as a ``ToolError``.

    ``functools.wraps`` keeps the signature and annotations the server reads to
    build the tool's schema and to find its context parameter.
    """

    @functools.wraps(tool_fn)
    async def _surfacing(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await tool_fn(*args, **kwargs)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    return _surfacing
