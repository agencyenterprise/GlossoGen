"""Shared OAuth record types used by every storage backend and the provider.

These ``NamedTuple`` shapes pair an MCP token/code with the ``group_id`` chosen
at consent time, plus the parked-consent request used in Clerk mode. They live
in their own module so the Postgres storage, the in-memory storage, and the
storage Protocol can all import them without an import cycle.
"""

from typing import NamedTuple
from uuid import UUID

from mcp.server.auth.provider import AccessToken, AuthorizationCode, RefreshToken


class AuthorizationCodeWithGroup(NamedTuple):
    """An authorization code plus the group_id chosen at consent time."""

    code: AuthorizationCode
    group_id: UUID


class RefreshTokenWithGroup(NamedTuple):
    """A refresh token plus its group_id."""

    token: RefreshToken
    group_id: UUID


class AccessTokenWithGroup(NamedTuple):
    """An access token plus its group_id."""

    token: AccessToken
    group_id: UUID


class PendingConsentRequest(NamedTuple):
    """OAuth authorization request waiting for Clerk-gated consent.

    Stored by ``authorize()`` in Clerk mode and consumed by the consent
    approval endpoint once the user has signed in and chosen a group.
    """

    request_id: str
    client_id: str
    scopes: list[str]
    code_challenge: str
    redirect_uri: str
    redirect_uri_provided_explicitly: bool
    resource: str | None
    state: str | None
