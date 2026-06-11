"""Per-request context for MCP tool calls.

The FastMCP sub-app is mounted inside the FastAPI app, but MCP tools are
plain async functions — they don't see ``Request`` and would otherwise rely
on module-level globals. ``RunContext`` carries the three values every tool
needs (runs directory, DB pool, active group_id) via a ``ContextVar`` set by
an ASGI wrapper around the sub-app.
"""

import logging
from contextvars import ContextVar
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

from schmidt.db.pool import DbPool

logger = logging.getLogger(__name__)


class RunContext(NamedTuple):
    """Resolved per-request state for an MCP tool call.

    ``pool`` is ``None`` in no-database local mode, where tools fall back to
    the filesystem-backed run helpers.
    """

    runs_dir: Path
    pool: DbPool | None
    group_id: UUID
    group_slug: str


_run_context: ContextVar[RunContext | None] = ContextVar("_mcp_run_context", default=None)


def get_run_context() -> RunContext:
    """Return the current request's ``RunContext`` (set by the ASGI wrapper).

    Raises ``RuntimeError`` if called outside an MCP request. That should be
    impossible in practice since FastMCP rejects unauthenticated requests
    before any tool runs.
    """
    ctx = _run_context.get()
    if ctx is None:
        raise RuntimeError(
            "RunContext not set — MCP tool invoked outside an authenticated MCP request"
        )
    return ctx


def set_run_context(ctx: RunContext) -> None:
    """Populate the contextvar; called by the MCP ASGI wrapper before delegating."""
    _run_context.set(ctx)
