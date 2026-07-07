"""ASGI wrapper that populates :class:`RunContext` for every MCP request.

Wraps the FastMCP sub-app. For each incoming HTTP request it reads the
bearer token from the ``Authorization`` header, looks up the token's
bound ``group_id`` via the OAuth storage, and stamps a fresh ``RunContext``
onto the contextvar so MCP tools can read it directly. Requests without a
valid token still pass through to FastMCP, which will reject them with 401.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from starlette.types import ASGIApp, Receive, Scope, Send

from glossogen.db.local_tenant import LOCAL_GROUP_SLUG
from glossogen.db.pool import DbPool
from glossogen.db.queries import get_group_by_id
from glossogen.server.mcp.oauth_provider import GlossoGenOAuthProvider
from glossogen.server.mcp.run_context import RunContext, set_run_context

logger = logging.getLogger(__name__)


class McpRunContextMiddleware:
    """ASGI middleware that primes :class:`RunContext` for MCP tool calls."""

    def __init__(
        self,
        app: ASGIApp,
        oauth_provider: GlossoGenOAuthProvider,
        get_pool: Callable[[], DbPool | None],
        get_runs_dir: Callable[[], Path],
    ) -> None:
        self.app = app
        self.oauth_provider = oauth_provider
        self.get_pool = get_pool
        self.get_runs_dir = get_runs_dir

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _bearer_token_from_scope(scope=scope)
        if token is not None:
            group_id = await self.oauth_provider.load_access_token_with_group(token=token)
            if group_id is not None:
                pool = self.get_pool()
                if pool is None:
                    # No-database local mode: the token is bound to the single
                    # local group, so the slug is the constant — no DB lookup.
                    set_run_context(
                        RunContext(
                            runs_dir=self.get_runs_dir(),
                            pool=None,
                            group_id=group_id,
                            group_slug=LOCAL_GROUP_SLUG,
                        )
                    )
                else:
                    async with pool.connection() as conn:
                        group = await get_group_by_id(conn=conn, group_id=group_id)
                    if group is not None:
                        set_run_context(
                            RunContext(
                                runs_dir=self.get_runs_dir(),
                                pool=pool,
                                group_id=group_id,
                                group_slug=group.slug,
                            )
                        )
        await self.app(scope, receive, send)


def _bearer_token_from_scope(scope: Scope) -> str | None:
    """Extract the ``Authorization: Bearer ...`` token from raw ASGI headers."""
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() == b"authorization":
            value = raw_value.decode("ascii", errors="replace")
            if value.startswith("Bearer "):
                token = value[len("Bearer ") :].strip()
                if token:
                    return token
    return None
