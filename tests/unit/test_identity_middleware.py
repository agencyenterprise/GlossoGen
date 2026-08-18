"""How the identity middleware answers, per credential and per path.

Built on :func:`create_app` with a fake provider, so no database and no clock is
involved: ``get_group_by_slug`` is replaced with a lookup over an in-memory dict, which
is the only thing the middleware asks the database for.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.requests import Request

from glossogen.db.local_tenant import LOCAL_GROUP_ID, LOCAL_USER_ID
from glossogen.db.rows import GroupRow
from glossogen.server import app_factory
from glossogen.server.app_factory import create_app
from glossogen.server.feature_flags import FeatureFlags
from glossogen.server.identity import middleware as middleware_module
from glossogen.server.identity.identity_provider import IdentityProvider
from glossogen.server.server_runtime_config import ServerRuntimeConfig
from tests.fakes.identity_provider import (
    FAKE_USER_ID,
    FAKE_WEBHOOK_PATH,
    FakeIdentityProvider,
    GroupForbiddingProvider,
)

KNOWN_SLUG = "team-a"
KNOWN_GROUP_ID = UUID("22222222-2222-4222-8222-222222222222")
ALLOWED_ORIGIN = "http://localhost:3000"


class ProbeResponse(BaseModel):
    """What a probe route reports back about the Identity it was handed."""

    user_id: str
    active_group_id: str


def group_row(slug: str, group_id: UUID) -> GroupRow:
    """Build one ``groups`` row."""
    return GroupRow(
        id=group_id,
        external_org_id=None,
        slug=slug,
        name=slug.title(),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture(autouse=True)
def known_groups_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the middleware's only database read with an in-memory lookup."""
    groups = {KNOWN_SLUG: group_row(slug=KNOWN_SLUG, group_id=KNOWN_GROUP_ID)}

    async def fake_get_group_by_slug(
        conn: object,  # noqa: ARG001 — signature-required
        slug: str,
    ) -> GroupRow | None:
        return groups.get(slug)

    monkeypatch.setattr(
        target=middleware_module,
        name="get_group_by_slug",
        value=fake_get_group_by_slug,
    )


class StubConnection:
    """Handed to the patched ``get_group_by_slug``, which never looks at it."""


class StubPool:
    """Enough of the pool for the middleware to borrow a connection.

    Not ``None``: the middleware borrows one unconditionally, and it is right to,
    because the lifespan refuses to boot a provider without a database. A ``None``
    here would test a state production cannot reach.
    """

    def connection(self) -> "StubPoolConnection":
        """Return an async context manager yielding a stub connection."""
        return StubPoolConnection()


class StubPoolConnection:
    """Async context manager yielding :class:`StubConnection`."""

    async def __aenter__(self) -> StubConnection:
        return StubConnection()

    async def __aexit__(self, *_args: object) -> None:
        return None


def build_app(tmp_path: Path, identity_provider: IdentityProvider | None) -> FastAPI:
    """Build an app with MCP disabled, so no OAuth machinery is involved."""
    app = create_app(
        identity_provider=identity_provider,
        runtime_config=ServerRuntimeConfig(
            runs_dir=tmp_path / "runs",
            oauth_issuer_url=None,
            allowed_origins=(ALLOWED_ORIGIN,),
            feature_flags=FeatureFlags(evaluations_enabled=True),
        ),
    )
    # The lifespan is what normally settles these, and it needs a real database.
    app.state.db_pool = StubPool()
    app.state.local_group_id = LOCAL_GROUP_ID
    return app


def add_probe_route(app: FastAPI) -> None:
    """Add a group-scoped route reporting the Identity the middleware attached."""

    @app.get("/api/g/{group_slug}/probe", response_model=ProbeResponse)
    async def probe(request: Request) -> ProbeResponse:  # pyright: ignore[reportUnusedFunction]
        identity = request.state.identity
        return ProbeResponse(
            user_id=identity.user_id,
            active_group_id=str(identity.active_group_id),
        )


def client_for(app: FastAPI) -> httpx.AsyncClient:
    """Return a client speaking ASGI directly to ``app``."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://identity.test",
    )


async def test_no_provider_stamps_the_local_identity(tmp_path: Path) -> None:
    """Single-tenant mode needs no credential and ignores the URL's slug."""
    app = build_app(tmp_path=tmp_path, identity_provider=None)
    add_probe_route(app=app)

    async with client_for(app) as client:
        response = await client.get("/api/g/anything-at-all/probe")

    assert response.status_code == 200
    assert response.json() == {
        "user_id": LOCAL_USER_ID,
        "active_group_id": str(LOCAL_GROUP_ID),
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/health",
        "/api/server-config",
        "/.well-known/oauth-authorization-server",
        "/.well-known/openid-configuration",
        "/mcp/anything",
    ],
)
async def test_the_unauthenticated_paths_need_no_credential(
    tmp_path: Path,
    path: str,
) -> None:
    """These bypass identity entirely, so they never answer 401."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    async with client_for(app) as client:
        response = await client.get(path)
    assert response.status_code != 401


async def test_a_provider_router_is_mounted_and_unauthenticated(tmp_path: Path) -> None:
    """A provider's own endpoint is reachable without a credential or a group slug."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    async with client_for(app) as client:
        response = await client.post(FAKE_WEBHOOK_PATH)
    assert response.status_code == 200
    assert response.json() == {"received": True}


async def test_a_missing_credential_is_401(tmp_path: Path) -> None:
    """With a provider installed, an anonymous request is unauthenticated."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    async with client_for(app) as client:
        response = await client.get(f"/api/g/{KNOWN_SLUG}/runs")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing bearer token"


async def test_a_path_without_a_group_slug_is_403(tmp_path: Path) -> None:
    """An authenticated route has to say which group it is acting in."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    async with client_for(app) as client:
        response = await client.get(
            "/api/runs",
            headers={"Authorization": "Bearer good-token"},
        )
    assert response.status_code == 403
    assert "/g/{group_slug}/" in response.json()["detail"]


async def test_an_unknown_group_slug_is_404(tmp_path: Path) -> None:
    """A slug no group owns is missing, not forbidden."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    async with client_for(app) as client:
        response = await client.get(
            "/api/g/no-such-group/runs",
            headers={"Authorization": "Bearer good-token"},
        )
    assert response.status_code == 404


async def test_an_unrecognised_credential_is_401(tmp_path: Path) -> None:
    """The provider's own rejection detail reaches the caller."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    async with client_for(app) as client:
        response = await client.get(
            f"/api/g/{KNOWN_SLUG}/runs",
            headers={"Authorization": "Bearer wrong-token"},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == "Fake credential not recognised"


async def test_a_rejected_group_surfaces_the_providers_own_403(tmp_path: Path) -> None:
    """A verified caller denied this group gets 403, not a blanket 401.

    The distinction matters to a client: it can refresh a token on 401 and cannot on
    403.
    """
    app = build_app(tmp_path=tmp_path, identity_provider=GroupForbiddingProvider())
    async with client_for(app) as client:
        response = await client.get(
            f"/api/g/{KNOWN_SLUG}/runs",
            headers={"Authorization": "Bearer good-token"},
        )
    assert response.status_code == 403
    assert KNOWN_SLUG in response.json()["detail"]


async def test_an_accepted_credential_stamps_the_providers_identity(tmp_path: Path) -> None:
    """A successful resolution attaches the Identity the provider built."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    add_probe_route(app=app)

    async with client_for(app) as client:
        response = await client.get(
            f"/api/g/{KNOWN_SLUG}/probe",
            headers={"Authorization": "Bearer good-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": FAKE_USER_ID,
        "active_group_id": str(KNOWN_GROUP_ID),
    }


async def test_an_sse_token_query_parameter_authenticates(tmp_path: Path) -> None:
    """``EventSource`` cannot set a header, so SSE carries the credential in the URL."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    add_probe_route(app=app)
    async with client_for(app) as client:
        rejected = await client.get(f"/api/g/{KNOWN_SLUG}/probe?token=wrong-token")
        accepted = await client.get(f"/api/g/{KNOWN_SLUG}/probe?token=good-token")
    assert rejected.status_code == 401
    assert accepted.status_code == 200


async def test_the_header_wins_over_the_query_parameter(tmp_path: Path) -> None:
    """Both present means the header is the one that counts."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    async with client_for(app) as client:
        response = await client.get(
            f"/api/g/{KNOWN_SLUG}/runs?token=good-token",
            headers={"Authorization": "Bearer wrong-token"},
        )
    assert response.status_code == 401


async def test_cors_headers_are_present_on_a_401(tmp_path: Path) -> None:
    """CORS has to be the outermost middleware, or a browser cannot read the 401.

    Pins the ordering in ``_add_middleware``: FastAPI applies middleware in reverse
    order of addition, so CORS being added last is what wraps the identity
    middleware's own rejections. Nothing else fails if that order is reversed.
    """
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    async with client_for(app) as client:
        response = await client.get(
            f"/api/g/{KNOWN_SLUG}/runs",
            headers={"Origin": ALLOWED_ORIGIN},
        )
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


async def test_an_options_request_passes_through(tmp_path: Path) -> None:
    """A CORS preflight carries no credential and must not be answered with 401."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    async with client_for(app) as client:
        response = await client.options(
            f"/api/g/{KNOWN_SLUG}/runs",
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code != 401


async def test_an_mcp_oauth_bearer_is_accepted_when_the_provider_rejects_it(tmp_path: Path) -> None:
    """An MCP token is not a session token, so the provider rejects it and OAuth wins."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())
    add_probe_route(app=app)

    class StubOAuthProvider:
        async def load_access_token_with_group(self, token: str) -> UUID | None:
            if token == "mcp-token":
                return KNOWN_GROUP_ID
            return None

    app.state.oauth_provider = StubOAuthProvider()

    async with client_for(app) as client:
        response = await client.get(
            f"/api/g/{KNOWN_SLUG}/probe",
            headers={"Authorization": "Bearer mcp-token"},
        )

    assert response.status_code == 200
    assert response.json()["user_id"] == "oauth:mcp-toke"


async def test_an_oauth_bearer_bound_to_another_group_is_rejected(tmp_path: Path) -> None:
    """A valid MCP token for a different group does not reach this one."""
    app = build_app(tmp_path=tmp_path, identity_provider=FakeIdentityProvider())

    class OtherGroupOAuthProvider:
        async def load_access_token_with_group(
            self,
            token: str,  # noqa: ARG002 — signature-required
        ) -> UUID | None:
            return uuid4()

    app.state.oauth_provider = OtherGroupOAuthProvider()

    async with client_for(app) as client:
        response = await client.get(
            f"/api/g/{KNOWN_SLUG}/runs",
            headers={"Authorization": "Bearer mcp-token"},
        )
    assert response.status_code == 401


async def test_a_403_is_not_retried_as_an_oauth_token(tmp_path: Path) -> None:
    """Re-reading a recognised credential as an MCP token cannot change a 403."""
    app = build_app(tmp_path=tmp_path, identity_provider=GroupForbiddingProvider())
    lookups: list[str] = []

    class RecordingOAuthProvider:
        async def load_access_token_with_group(self, token: str) -> UUID | None:
            lookups.append(token)
            return KNOWN_GROUP_ID

    app.state.oauth_provider = RecordingOAuthProvider()

    async with client_for(app) as client:
        response = await client.get(
            f"/api/g/{KNOWN_SLUG}/runs",
            headers={"Authorization": "Bearer good-token"},
        )
    assert response.status_code == 403
    assert lookups == []


def test_the_declared_prefixes_cover_the_contributed_routes() -> None:
    """A provider's contributed paths must be covered by the prefixes it declares.

    Declaring a router but forgetting the prefix leaves an endpoint its identity
    service calls answering 401 or 403 forever.
    """
    provider = FakeIdentityProvider()
    prefixes = provider.unauthenticated_path_prefixes()
    for router in provider.routers():
        for route in router.routes:
            path = getattr(route, "path", "")
            assert any(path.startswith(prefix) for prefix in prefixes), path


def test_the_factory_is_importable_without_building_the_module_level_app() -> None:
    """``create_app`` is reachable without importing ``glossogen.server.app``.

    What lets the export script pin the provider off, and what lets every test above
    build an app of its own.
    """
    assert app_factory.create_app is create_app
