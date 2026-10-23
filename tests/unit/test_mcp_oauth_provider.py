"""How the MCP OAuth provider issues, binds, rotates and revokes what it mints.

Backed by the in-memory storage, which is what no-database local mode runs on and
which mirrors the Postgres storage's expiry and client checks. The group a token is
bound to decides which runs an MCP tool call can see, so most of these follow a
group id from consent to the access token.
"""

import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from mcp.server.auth.provider import (
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from glossogen.server.mcp import in_memory_oauth_storage, oauth_provider
from glossogen.server.mcp.in_memory_oauth_storage import InMemoryOAuthStorage
from glossogen.server.mcp.oauth_provider import GlossoGenOAuthProvider
from glossogen.server.mcp.oauth_storage import (
    ACCESS_TOKEN_LIFETIME,
    AUTHORIZATION_CODE_LIFETIME,
    PENDING_CONSENT_LIFETIME,
)
from tests.fakes.identity_provider import FakeIdentityProvider

RESOURCE = "https://example.test/mcp"
CALLBACK = "http://127.0.0.1/callback"


def _provider(storage: InMemoryOAuthStorage, group_id: UUID) -> GlossoGenOAuthProvider:
    return GlossoGenOAuthProvider(
        storage=storage,
        get_local_group_id=lambda: group_id,
        identity_provider=None,
        resource_server_url=RESOURCE,
    )


def _multi_tenant_provider(storage: InMemoryOAuthStorage) -> GlossoGenOAuthProvider:
    """A provider with an identity provider installed, so consent is deferred."""

    def no_local_group() -> UUID:
        raise AssertionError("multi-tenant consent must not fall back to the local group")

    return GlossoGenOAuthProvider(
        storage=storage,
        get_local_group_id=no_local_group,
        identity_provider=FakeIdentityProvider(),
        resource_server_url=RESOURCE,
    )


async def _registered_client(
    storage: InMemoryOAuthStorage, client_id: str
) -> OAuthClientInformationFull:
    client = OAuthClientInformationFull(
        client_id=client_id,
        redirect_uris=[AnyUrl(CALLBACK)],
        token_endpoint_auth_method="none",
    )
    await storage.save_client(client=client)
    return client


def _params(resource: str | None) -> AuthorizationParams:
    return AuthorizationParams(
        state="state-123",
        scopes=["read"],
        code_challenge="challenge",
        redirect_uri=AnyUrl(CALLBACK),
        redirect_uri_provided_explicitly=True,
        resource=resource,
    )


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


async def _issue_tokens(
    provider: GlossoGenOAuthProvider, client: OAuthClientInformationFull
) -> OAuthToken:
    """Run authorize and the code exchange the way the SDK's handlers call them."""
    redirect = await provider.authorize(client=client, params=_params(resource=None))
    code = await provider.load_authorization_code(
        client=client, authorization_code=_query(url=redirect)["code"][0]
    )
    assert code is not None
    return await provider.exchange_authorization_code(client=client, authorization_code=code)


class FakeClock:
    """Stands in for the ``time`` module in the provider and the storage."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def time(self) -> float:
        """Return the current fake epoch."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Move the clock forward."""
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    """Drive expiry explicitly instead of waiting for it."""
    fake = FakeClock()
    fake_time = SimpleNamespace(time=fake.time)
    monkeypatch.setattr(target=in_memory_oauth_storage, name="time", value=fake_time)
    monkeypatch.setattr(target=oauth_provider, name="time", value=fake_time)
    return fake


async def test_authorization_defaults_an_omitted_resource_to_this_server() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")

    redirect = await provider.authorize(client=client, params=_params(resource=None))

    code = _query(url=redirect)["code"][0]
    stored = await storage.load_authorization_code(client_id="client", code=code)
    assert stored is not None
    assert stored.code.resource == RESOURCE


async def test_refresh_preserves_the_resource_indicator() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")

    issued = await _issue_tokens(provider=provider, client=client)
    first_access = await storage.load_access_token(token=issued.access_token)
    assert issued.refresh_token is not None
    first_refresh = await storage.load_refresh_token(client_id="client", token=issued.refresh_token)
    assert first_access is not None
    assert first_access.token.resource == RESOURCE
    assert first_refresh is not None
    assert first_refresh.token.resource == RESOURCE

    rotated = await provider.exchange_refresh_token(
        client=client, refresh_token=first_refresh.token, scopes=[]
    )
    rotated_access = await storage.load_access_token(token=rotated.access_token)
    assert rotated.refresh_token is not None
    rotated_refresh = await storage.load_refresh_token(
        client_id="client", token=rotated.refresh_token
    )
    assert rotated_access is not None
    assert rotated_access.token.resource == RESOURCE
    assert rotated_refresh is not None
    assert rotated_refresh.token.resource == RESOURCE


async def test_refresh_upgrades_a_token_issued_before_resource_storage() -> None:
    storage = InMemoryOAuthStorage()
    group_id = uuid4()
    client = await _registered_client(storage=storage, client_id="client")
    legacy = RefreshToken(
        token="legacy-refresh",
        client_id="client",
        scopes=["read"],
        resource=None,
        expires_at=int(time.time()) + 60,
    )
    await storage.save_refresh_token(token=legacy, group_id=group_id)

    issued = await _provider(storage=storage, group_id=group_id).exchange_refresh_token(
        client=client, refresh_token=legacy, scopes=[]
    )

    access = await storage.load_access_token(token=issued.access_token)
    assert issued.refresh_token is not None
    refresh = await storage.load_refresh_token(client_id="client", token=issued.refresh_token)
    assert access is not None
    assert access.token.resource == RESOURCE
    assert refresh is not None
    assert refresh.token.resource == RESOURCE


async def test_local_mode_binds_the_issued_access_token_to_the_local_group() -> None:
    storage = InMemoryOAuthStorage()
    local_group = uuid4()
    provider = _provider(storage=storage, group_id=local_group)
    client = await _registered_client(storage=storage, client_id="client")

    issued = await _issue_tokens(provider=provider, client=client)

    assert await provider.load_access_token_with_group(token=issued.access_token) == local_group
    assert issued.scope == "read"


async def test_the_redirect_carries_the_clients_state() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")

    redirect = await provider.authorize(client=client, params=_params(resource=None))

    assert redirect.startswith(CALLBACK)
    assert _query(url=redirect)["state"] == ["state-123"]


async def test_a_resource_for_another_server_is_refused() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")

    with pytest.raises(AuthorizeError) as refused:
        await provider.authorize(
            client=client, params=_params(resource="https://elsewhere.test/mcp")
        )

    assert refused.value.error == "invalid_request"


async def test_a_trailing_slash_on_the_resource_names_this_server() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")

    redirect = await provider.authorize(client=client, params=_params(resource=f"{RESOURCE}/"))

    stored = await storage.load_authorization_code(
        client_id="client", code=_query(url=redirect)["code"][0]
    )
    assert stored is not None
    assert stored.code.resource == RESOURCE


async def test_an_authorization_code_is_single_use() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")
    redirect = await provider.authorize(client=client, params=_params(resource=None))
    code = await provider.load_authorization_code(
        client=client, authorization_code=_query(url=redirect)["code"][0]
    )
    assert code is not None

    await provider.exchange_authorization_code(client=client, authorization_code=code)

    assert (
        await provider.load_authorization_code(client=client, authorization_code=code.code) is None
    )
    with pytest.raises(AuthorizeError):
        await provider.exchange_authorization_code(client=client, authorization_code=code)


async def test_a_code_issued_to_one_client_does_not_load_for_another() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    owner = await _registered_client(storage=storage, client_id="owner")
    other = await _registered_client(storage=storage, client_id="other")
    redirect = await provider.authorize(client=owner, params=_params(resource=None))

    code = _query(url=redirect)["code"][0]

    assert await provider.load_authorization_code(client=other, authorization_code=code) is None
    assert await provider.load_authorization_code(client=owner, authorization_code=code) is not None


async def test_an_expired_authorization_code_does_not_load(clock: FakeClock) -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")
    redirect = await provider.authorize(client=client, params=_params(resource=None))

    clock.advance(seconds=AUTHORIZATION_CODE_LIFETIME + 1)

    code = _query(url=redirect)["code"][0]
    assert await provider.load_authorization_code(client=client, authorization_code=code) is None


async def test_an_expired_access_token_resolves_to_no_group(clock: FakeClock) -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")
    issued = await _issue_tokens(provider=provider, client=client)

    clock.advance(seconds=ACCESS_TOKEN_LIFETIME + 1)

    assert await provider.load_access_token(token=issued.access_token) is None
    assert await provider.load_access_token_with_group(token=issued.access_token) is None


async def test_refresh_rotates_the_refresh_token_and_keeps_the_group() -> None:
    storage = InMemoryOAuthStorage()
    local_group = uuid4()
    provider = _provider(storage=storage, group_id=local_group)
    client = await _registered_client(storage=storage, client_id="client")
    issued = await _issue_tokens(provider=provider, client=client)
    assert issued.refresh_token is not None
    refresh = await provider.load_refresh_token(client=client, refresh_token=issued.refresh_token)
    assert refresh is not None

    rotated = await provider.exchange_refresh_token(client=client, refresh_token=refresh, scopes=[])

    assert await provider.load_refresh_token(client=client, refresh_token=refresh.token) is None
    assert rotated.refresh_token is not None
    assert rotated.refresh_token != refresh.token
    assert await provider.load_access_token_with_group(token=rotated.access_token) == local_group
    with pytest.raises(AuthorizeError):
        await provider.exchange_refresh_token(client=client, refresh_token=refresh, scopes=[])


async def test_refresh_narrows_to_the_scopes_asked_for() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")
    refresh = RefreshToken(
        token="refresh",
        client_id="client",
        scopes=["read", "write"],
        resource=RESOURCE,
        expires_at=int(time.time()) + 60,
    )
    await storage.save_refresh_token(token=refresh, group_id=uuid4())

    rotated = await provider.exchange_refresh_token(
        client=client, refresh_token=refresh, scopes=["read"]
    )

    assert rotated.scope == "read"


async def test_revoking_an_access_token_also_drops_the_clients_refresh_tokens() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")
    issued = await _issue_tokens(provider=provider, client=client)
    assert issued.refresh_token is not None
    access = await provider.load_access_token(token=issued.access_token)
    assert access is not None

    await provider.revoke_token(token=access)

    assert await provider.load_access_token(token=issued.access_token) is None
    assert (
        await provider.load_refresh_token(client=client, refresh_token=issued.refresh_token) is None
    )


async def test_revoking_a_refresh_token_also_drops_the_clients_access_tokens() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    client = await _registered_client(storage=storage, client_id="client")
    issued = await _issue_tokens(provider=provider, client=client)
    assert issued.refresh_token is not None
    refresh = await provider.load_refresh_token(client=client, refresh_token=issued.refresh_token)
    assert refresh is not None

    await provider.revoke_token(token=refresh)

    assert await provider.load_refresh_token(client=client, refresh_token=refresh.token) is None
    assert await provider.load_access_token(token=issued.access_token) is None


async def test_revocation_leaves_other_clients_tokens_alone() -> None:
    storage = InMemoryOAuthStorage()
    provider = _provider(storage=storage, group_id=uuid4())
    revoked = await _registered_client(storage=storage, client_id="revoked")
    bystander = await _registered_client(storage=storage, client_id="bystander")
    revoked_tokens = await _issue_tokens(provider=provider, client=revoked)
    kept = await _issue_tokens(provider=provider, client=bystander)
    access = await provider.load_access_token(token=revoked_tokens.access_token)
    assert access is not None
    assert kept.refresh_token is not None

    await provider.revoke_token(token=access)

    assert await provider.load_access_token(token=kept.access_token) is not None
    assert (
        await provider.load_refresh_token(client=bystander, refresh_token=kept.refresh_token)
        is not None
    )


async def test_multi_tenant_authorize_parks_the_request_instead_of_issuing_a_code() -> None:
    storage = InMemoryOAuthStorage()
    provider = _multi_tenant_provider(storage=storage)
    client = await _registered_client(storage=storage, client_id="client")

    consent_url = await provider.authorize(client=client, params=_params(resource=None))

    assert consent_url.startswith("https://fake-provider.test/consent")
    request_id = _query(url=consent_url)["request_id"][0]
    pending = await storage.load_pending_consent(request_id=request_id)
    assert pending is not None
    assert pending.client_id == "client"
    assert pending.resource == RESOURCE
    assert "code" not in _query(url=consent_url)


async def test_approved_consent_binds_the_tokens_to_the_chosen_group() -> None:
    storage = InMemoryOAuthStorage()
    provider = _multi_tenant_provider(storage=storage)
    client = await _registered_client(storage=storage, client_id="client")
    consent_url = await provider.authorize(client=client, params=_params(resource=None))
    chosen_group = uuid4()

    redirect = await provider.approve_pending_consent(
        request_id=_query(url=consent_url)["request_id"][0], group_id=chosen_group
    )

    assert redirect.startswith(CALLBACK)
    assert _query(url=redirect)["state"] == ["state-123"]
    code = await provider.load_authorization_code(
        client=client, authorization_code=_query(url=redirect)["code"][0]
    )
    assert code is not None
    issued = await provider.exchange_authorization_code(client=client, authorization_code=code)
    assert await provider.load_access_token_with_group(token=issued.access_token) == chosen_group


async def test_a_consent_request_can_be_approved_once() -> None:
    storage = InMemoryOAuthStorage()
    provider = _multi_tenant_provider(storage=storage)
    client = await _registered_client(storage=storage, client_id="client")
    consent_url = await provider.authorize(client=client, params=_params(resource=None))
    request_id = _query(url=consent_url)["request_id"][0]
    await provider.approve_pending_consent(request_id=request_id, group_id=uuid4())

    with pytest.raises(AuthorizeError) as refused:
        await provider.approve_pending_consent(request_id=request_id, group_id=uuid4())

    assert refused.value.error == "access_denied"


async def test_an_expired_consent_request_cannot_be_approved(clock: FakeClock) -> None:
    storage = InMemoryOAuthStorage()
    provider = _multi_tenant_provider(storage=storage)
    client = await _registered_client(storage=storage, client_id="client")
    consent_url = await provider.authorize(client=client, params=_params(resource=None))

    clock.advance(seconds=PENDING_CONSENT_LIFETIME + 1)

    with pytest.raises(AuthorizeError):
        await provider.approve_pending_consent(
            request_id=_query(url=consent_url)["request_id"][0], group_id=uuid4()
        )


async def test_consent_for_a_client_that_has_gone_is_refused() -> None:
    storage = InMemoryOAuthStorage()
    provider = _multi_tenant_provider(storage=storage)
    client = OAuthClientInformationFull(
        client_id="never-registered",
        redirect_uris=[AnyUrl(CALLBACK)],
        token_endpoint_auth_method="none",
    )
    consent_url = await provider.authorize(client=client, params=_params(resource=None))

    with pytest.raises(AuthorizeError) as refused:
        await provider.approve_pending_consent(
            request_id=_query(url=consent_url)["request_id"][0], group_id=uuid4()
        )

    assert "never-registered" in str(refused.value.error_description)
