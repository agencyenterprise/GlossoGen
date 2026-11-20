"""What the consent page learns about a parked MCP authorization request.

Client registration is open, so anyone can register a client whose redirect URI is
their own server and send a signed-in user the authorization link. Approving it sends
the code to that server, and with it a token for the user's group. These tests run that
flow through the SDK's own handlers and check the consent page is told where the code
will go before the user approves.
"""

import base64
import hashlib
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
from fastapi import FastAPI
from mcp.server.transport_security import TransportSecuritySettings

from glossogen.server.mcp.browser import _build_mcp_server  # pyright: ignore[reportPrivateUsage]
from glossogen.server.mcp.consent_request_router import router
from glossogen.server.mcp.in_memory_oauth_storage import InMemoryOAuthStorage
from glossogen.server.mcp.oauth_provider import GlossoGenOAuthProvider
from tests.fakes.identity_provider import FakeIdentityProvider

RESOURCE = "https://example.test/mcp"
FOREIGN_CALLBACK = "https://collector.example/cb"
VERIFIER = "v" * 64


def _multi_tenant_provider() -> GlossoGenOAuthProvider:
    """A provider with an identity provider installed, so consent is deferred."""
    return GlossoGenOAuthProvider(
        storage=InMemoryOAuthStorage(),
        get_local_group_id=uuid4,
        identity_provider=FakeIdentityProvider(),
        resource_server_url=RESOURCE,
    )


def _mcp_http_client(provider: GlossoGenOAuthProvider) -> httpx.AsyncClient:
    """An HTTP client for the MCP sub-app, so requests go through the SDK's handlers."""
    app = _build_mcp_server(oauth_provider=provider, issuer_url=RESOURCE).streamable_http_app(
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://example.test"
    )


def _challenge() -> str:
    digest = hashlib.sha256(VERIFIER.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _consent_client(provider: GlossoGenOAuthProvider) -> httpx.AsyncClient:
    """An HTTP client for an app carrying only the consent-request route."""
    app = FastAPI()
    app.state.oauth_provider = provider
    app.include_router(router)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://api.test")


async def _park_request_from_foreign_client(provider: GlossoGenOAuthProvider) -> str:
    """Register a client named like the CLI with a foreign callback and authorize it."""
    async with _mcp_http_client(provider=provider) as mcp:
        registered = await mcp.post(
            "/register",
            json={
                "redirect_uris": [FOREIGN_CALLBACK],
                "token_endpoint_auth_method": "none",
                "client_name": "glossogen CLI",
            },
        )
        assert registered.status_code == 201
        authorized = await mcp.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": registered.json()["client_id"],
                "redirect_uri": FOREIGN_CALLBACK,
                "code_challenge": _challenge(),
                "code_challenge_method": "S256",
                "state": "s",
                "scope": "read write",
            },
        )
    assert authorized.status_code == 302
    return parse_qs(urlparse(authorized.headers["location"]).query)["request_id"][0]


async def test_the_consent_page_is_told_where_the_code_will_go() -> None:
    provider = _multi_tenant_provider()
    request_id = await _park_request_from_foreign_client(provider=provider)

    async with _consent_client(provider=provider) as api:
        response = await api.get(f"/mcp/consent-request/{request_id}")

    assert response.status_code == 200
    assert response.json() == {
        "client_name": "glossogen CLI",
        "redirect_uri": FOREIGN_CALLBACK,
        "scopes": ["read", "write"],
    }


async def test_an_approved_request_is_no_longer_described() -> None:
    provider = _multi_tenant_provider()
    request_id = await _park_request_from_foreign_client(provider=provider)
    await provider.approve_pending_consent(
        request_id=request_id,
        group_id=uuid4(),
    )

    async with _consent_client(provider=provider) as api:
        response = await api.get(f"/mcp/consent-request/{request_id}")

    assert response.status_code == 404


async def test_an_unknown_request_is_not_found() -> None:
    provider = _multi_tenant_provider()

    async with _consent_client(provider=provider) as api:
        response = await api.get("/mcp/consent-request/never-parked")

    assert response.status_code == 404


async def test_without_an_oauth_provider_the_route_answers_503() -> None:
    app = FastAPI()
    app.include_router(router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://api.test"
    ) as api:
        response = await api.get("/mcp/consent-request/anything")

    assert response.status_code == 503
