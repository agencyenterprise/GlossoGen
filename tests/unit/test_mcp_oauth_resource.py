"""OAuth tokens remain bound to the requested MCP resource after refresh."""

import time
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from mcp.server.auth.provider import AuthorizationCode, AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from glossogen.server.mcp.in_memory_oauth_storage import InMemoryOAuthStorage
from glossogen.server.mcp.oauth_provider import GlossoGenOAuthProvider


def _provider(storage: InMemoryOAuthStorage, group_id: UUID) -> GlossoGenOAuthProvider:
    return GlossoGenOAuthProvider(
        storage=storage,
        get_local_group_id=lambda: group_id,
        identity_provider=None,
        resource_server_url="https://example.test/mcp",
    )


async def test_authorization_defaults_an_omitted_resource_to_this_server() -> None:
    storage = InMemoryOAuthStorage()
    group_id = uuid4()
    client = OAuthClientInformationFull(
        client_id="client",
        redirect_uris=[AnyUrl("http://127.0.0.1/callback")],
        token_endpoint_auth_method="none",
    )
    redirect = await _provider(storage=storage, group_id=group_id).authorize(
        client=client,
        params=AuthorizationParams(
            state="state",
            scopes=["read"],
            code_challenge="challenge",
            redirect_uri=AnyUrl("http://127.0.0.1/callback"),
            redirect_uri_provided_explicitly=True,
            resource=None,
        ),
    )

    code = parse_qs(urlparse(redirect).query)["code"][0]
    stored = await storage.load_authorization_code(client_id=client.client_id, code=code)
    assert stored is not None
    assert stored.code.resource == "https://example.test/mcp"


async def test_refresh_preserves_the_resource_indicator() -> None:
    storage = InMemoryOAuthStorage()
    group_id = uuid4()
    client = OAuthClientInformationFull(
        client_id="client",
        redirect_uris=[AnyUrl("http://127.0.0.1/callback")],
        token_endpoint_auth_method="none",
    )
    code = AuthorizationCode(
        code="authorization-code",
        client_id=client.client_id,
        scopes=["read"],
        code_challenge="challenge",
        redirect_uri=AnyUrl("http://127.0.0.1/callback"),
        redirect_uri_provided_explicitly=True,
        resource="https://example.test/mcp",
        expires_at=time.time() + 60,
    )
    await storage.save_authorization_code(code=code, group_id=group_id)
    provider = _provider(storage=storage, group_id=group_id)

    issued = await provider.exchange_authorization_code(client=client, authorization_code=code)
    first_access = await storage.load_access_token(token=issued.access_token)
    first_refresh = await storage.load_refresh_token(
        client_id=client.client_id,
        token=issued.refresh_token or "",
    )
    assert first_access is not None
    assert first_access.token.resource == "https://example.test/mcp"
    assert first_refresh is not None
    assert first_refresh.token.resource == "https://example.test/mcp"

    rotated = await provider.exchange_refresh_token(
        client=client,
        refresh_token=first_refresh.token,
        scopes=[],
    )
    rotated_access = await storage.load_access_token(token=rotated.access_token)
    rotated_refresh = await storage.load_refresh_token(
        client_id=client.client_id,
        token=rotated.refresh_token or "",
    )
    assert rotated_access is not None
    assert rotated_access.token.resource == "https://example.test/mcp"
    assert rotated_refresh is not None
    assert rotated_refresh.token.resource == "https://example.test/mcp"
