"""What :class:`McpRunContextMiddleware` hands an MCP tool, per bearer token.

The middleware is what scopes an MCP tool call to a group: it resolves the request's
access token to the group bound at consent and stamps that onto the ``RunContext``.
The inner app here stands in for FastMCP and records the context it sees. The one
database read, ``get_group_by_id``, is replaced with a lookup over a dict.
"""

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from mcp.server.auth.provider import AccessToken
from starlette.types import Receive, Scope, Send

from glossogen.db.local_tenant import LOCAL_GROUP_SLUG
from glossogen.db.pool import DbPool
from glossogen.db.rows import GroupRow
from glossogen.server.mcp import asgi_context
from glossogen.server.mcp.asgi_context import McpRunContextMiddleware
from glossogen.server.mcp.in_memory_oauth_storage import InMemoryOAuthStorage
from glossogen.server.mcp.oauth_provider import GlossoGenOAuthProvider
from glossogen.server.mcp.run_context import RunContext, get_run_context

KNOWN_GROUP_ID = UUID("33333333-3333-4333-8333-333333333333")
KNOWN_SLUG = "team-b"


class ContextRecordingApp:
    """Records the ``RunContext`` each request reached it with, or ``None``."""

    def __init__(self) -> None:
        self.seen: list[RunContext | None] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        _ = (scope, receive, send)
        try:
            self.seen.append(get_run_context())
        except RuntimeError:
            self.seen.append(None)


class StubPoolConnection:
    """Async context manager yielding a connection nothing looks at."""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *_args: object) -> None:
        return None


class StubPool:
    """Enough of the pool for the middleware to borrow a connection."""

    def connection(self) -> StubPoolConnection:
        """Return an async context manager yielding a stub connection."""
        return StubPoolConnection()


def _stub_pool() -> DbPool:
    """A :class:`StubPool` typed as the pool the middleware is given."""
    return cast(DbPool, StubPool())


@pytest.fixture(autouse=True)
def known_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the middleware's only database read with an in-memory lookup."""
    groups = {
        KNOWN_GROUP_ID: GroupRow(
            id=KNOWN_GROUP_ID,
            external_org_id=None,
            slug=KNOWN_SLUG,
            name="Team B",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    }

    async def fake_get_group_by_id(
        conn: object,  # noqa: ARG001 — signature-required
        group_id: UUID,
    ) -> GroupRow | None:
        return groups.get(group_id)

    monkeypatch.setattr(target=asgi_context, name="get_group_by_id", value=fake_get_group_by_id)


async def _storage_with_token(token: str, group_id: UUID) -> InMemoryOAuthStorage:
    storage = InMemoryOAuthStorage()
    await storage.save_access_token(
        token=AccessToken(
            token=token,
            client_id="client",
            scopes=["read"],
            resource="https://example.test/mcp",
            expires_at=int(time.time()) + 3600,
        ),
        group_id=group_id,
    )
    return storage


def _middleware(
    storage: InMemoryOAuthStorage,
    inner: ContextRecordingApp,
    pool: DbPool | None,
    runs_dir: Path,
) -> McpRunContextMiddleware:
    provider = GlossoGenOAuthProvider(
        storage=storage,
        get_local_group_id=uuid4,
        identity_provider=None,
        resource_server_url="https://example.test/mcp",
    )
    return McpRunContextMiddleware(
        app=inner,
        oauth_provider=provider,
        get_pool=lambda: pool,
        get_runs_dir=lambda: runs_dir,
    )


async def _call(middleware: McpRunContextMiddleware, authorization: str | None) -> None:
    headers: list[tuple[bytes, bytes]] = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode("ascii")))
    scope: Scope = {"type": "http", "method": "POST", "path": "/", "headers": headers}

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: object) -> None:
        return None

    await middleware(scope, receive, send)


async def test_a_valid_token_without_a_database_scopes_the_call_to_the_local_group(
    tmp_path: Path,
) -> None:
    group_id = uuid4()
    inner = ContextRecordingApp()
    middleware = _middleware(
        storage=await _storage_with_token(token="tok", group_id=group_id),
        inner=inner,
        pool=None,
        runs_dir=tmp_path,
    )

    await _call(middleware=middleware, authorization="Bearer tok")

    assert inner.seen == [
        RunContext(runs_dir=tmp_path, pool=None, group_id=group_id, group_slug=LOCAL_GROUP_SLUG)
    ]


async def test_a_valid_token_with_a_database_carries_its_groups_slug(tmp_path: Path) -> None:
    inner = ContextRecordingApp()
    pool = _stub_pool()
    middleware = _middleware(
        storage=await _storage_with_token(token="tok", group_id=KNOWN_GROUP_ID),
        inner=inner,
        pool=pool,
        runs_dir=tmp_path,
    )

    await _call(middleware=middleware, authorization="Bearer tok")

    assert inner.seen == [
        RunContext(runs_dir=tmp_path, pool=pool, group_id=KNOWN_GROUP_ID, group_slug=KNOWN_SLUG)
    ]


async def test_a_token_bound_to_a_group_the_database_lacks_sets_no_context(
    tmp_path: Path,
) -> None:
    inner = ContextRecordingApp()
    middleware = _middleware(
        storage=await _storage_with_token(token="tok", group_id=uuid4()),
        inner=inner,
        pool=_stub_pool(),
        runs_dir=tmp_path,
    )

    await _call(middleware=middleware, authorization="Bearer tok")

    assert inner.seen == [None]


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer unknown-token", "Bearer ", "Basic dG9rOg=="],
)
async def test_a_request_without_a_valid_bearer_still_reaches_the_app_with_no_context(
    tmp_path: Path,
    authorization: str | None,
) -> None:
    """FastMCP answers these with 401; the middleware only declines to scope them."""
    inner = ContextRecordingApp()
    middleware = _middleware(
        storage=await _storage_with_token(token="tok", group_id=uuid4()),
        inner=inner,
        pool=None,
        runs_dir=tmp_path,
    )

    await _call(middleware=middleware, authorization=authorization)

    assert inner.seen == [None]


@pytest.mark.parametrize("scheme", ["bearer", "BEARER"])
@pytest.mark.xfail(
    strict=True,
    reason=(
        "asgi_context._bearer_token_from_scope matches 'Bearer ' case-sensitively, while "
        "the MCP SDK's BearerAuthBackend accepts any case, so a 'bearer' request passes "
        "authentication and reaches the tool with no RunContext"
    ),
)
async def test_the_bearer_scheme_is_matched_case_insensitively(
    tmp_path: Path,
    scheme: str,
) -> None:
    """The MCP SDK authenticates any case of the scheme, so the context must follow."""
    group_id = uuid4()
    inner = ContextRecordingApp()
    middleware = _middleware(
        storage=await _storage_with_token(token="tok", group_id=group_id),
        inner=inner,
        pool=None,
        runs_dir=tmp_path,
    )

    await _call(middleware=middleware, authorization=f"{scheme} tok")

    assert inner.seen == [
        RunContext(runs_dir=tmp_path, pool=None, group_id=group_id, group_slug=LOCAL_GROUP_SLUG)
    ]
