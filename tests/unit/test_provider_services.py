"""The half of the identity seam the platform offers a provider.

Nothing in this repository calls these, by design: their callers live in whichever
distribution supplies the identity provider. That makes them the easiest part of the
contract to break without noticing, which is what these tests are for.
"""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from mcp.server.auth.provider import AuthorizeError
from starlette.requests import Request

from glossogen.server.identity.provider_services import (
    ConsentNotApprovable,
    approve_parked_consent,
    frontend_base_url,
)

REDIRECT = "https://client.test/callback?code=abc&state=xyz"


class StubOAuthProvider:
    """Stands in for the platform's OAuth provider, recording what it was asked."""

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, UUID]] = []

    async def approve_pending_consent(self, request_id: str, group_id: UUID) -> str:
        """Return the configured redirect, or raise the configured error."""
        self.calls.append((request_id, group_id))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return str(self.outcome)


def request_with(oauth_provider: object | None) -> Request:
    """Build a request whose ``app.state`` carries ``oauth_provider``.

    Assembled by hand rather than through a client: these functions read one
    attribute off ``app.state`` and nothing else, so a full app would obscure how
    little they touch. ``None`` leaves the attribute absent, which is the shape
    ``create_app`` produces when MCP is not mounted.
    """
    state = SimpleNamespace()
    if oauth_provider is not None:
        state.oauth_provider = oauth_provider
    app = SimpleNamespace(state=state)
    return Request(scope={"type": "http", "app": app, "headers": []})


def test_frontend_base_url_prefers_the_explicit_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``FRONTEND_URL`` wins, and its trailing slash is dropped."""
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com/")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://ignored.example.com")
    assert frontend_base_url() == "https://app.example.com"


def test_frontend_base_url_falls_back_to_the_first_allowed_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no explicit value, the first CORS origin is the frontend."""
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://first.example.com/, https://second.example.com")
    assert frontend_base_url() == "https://first.example.com"


def test_frontend_base_url_ignores_a_blank_explicit_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty or whitespace ``FRONTEND_URL`` is not a value.

    A variable set to the empty string is what an unfilled deployment template looks
    like, and treating it as an answer would send consent redirects to an empty host.
    """
    monkeypatch.setenv("FRONTEND_URL", "   ")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://first.example.com")
    assert frontend_base_url() == "https://first.example.com"


def test_frontend_base_url_defaults_to_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither variable set is the local-development case."""
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert frontend_base_url() == "http://localhost:3000"


async def test_approve_parked_consent_returns_the_client_redirect() -> None:
    """The happy path hands back the URL the user-agent should follow."""
    stub = StubOAuthProvider(outcome=REDIRECT)
    group_id = uuid4()

    result = await approve_parked_consent(
        request=request_with(oauth_provider=stub),
        request_id="req-1",
        group_id=group_id,
    )

    assert result == REDIRECT
    # The group is the provider's decision and the only reason the request was parked,
    # so it has to reach the platform unchanged.
    assert stub.calls == [("req-1", group_id)]


async def test_an_expired_or_reused_link_raises_consent_not_approvable() -> None:
    """The MCP library's error is translated at the seam.

    A provider handling an expired link must not have to import from
    ``mcp.server.auth`` to catch it, and the distinction matters because this one is
    the caller's problem rather than the server's.
    """
    stub = StubOAuthProvider(
        outcome=AuthorizeError(
            error="access_denied",
            error_description="Consent request expired or already used",
        )
    )

    with pytest.raises(ConsentNotApprovable, match="expired or already used"):
        await approve_parked_consent(
            request=request_with(oauth_provider=stub),
            request_id="req-gone",
            group_id=uuid4(),
        )


async def test_an_unconfigured_mcp_raises_runtime_error() -> None:
    """No OAuth provider on the app means no consent request can have been parked.

    Deliberately not ``ConsentNotApprovable``: this is a deployment mistake, not a
    stale link, and a provider should answer 5xx rather than telling the caller to
    try again.
    """
    with pytest.raises(RuntimeError, match="OAUTH_ISSUER_URL"):
        await approve_parked_consent(
            request=request_with(oauth_provider=None),
            request_id="req-1",
            group_id=uuid4(),
        )


def test_consent_not_approvable_does_not_leak_the_library_type() -> None:
    """The seam's exception is the platform's own, not the MCP library's.

    If these were ever unified, a provider catching ``ConsentNotApprovable`` would
    silently start needing an ``mcp`` import to name what it caught.
    """
    assert not issubclass(ConsentNotApprovable, AuthorizeError)
