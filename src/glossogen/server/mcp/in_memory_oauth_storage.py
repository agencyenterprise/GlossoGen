"""In-memory OAuth storage for no-database local mode.

Holds OAuth clients, authorization codes, access/refresh tokens, and parked
consent requests in process-local dicts. Tokens do not survive a server
restart — acceptable for single-user local development, where the MCP client
simply re-authenticates. Prod uses the Postgres-backed
:class:`~glossogen.server.mcp.oauth_storage.OAuthStorage` instead.

Expiry mirrors the Postgres backend: a load that finds an expired record
deletes it and returns ``None``.
"""

import logging
import time
from uuid import UUID

from mcp.server.auth.provider import AccessToken, AuthorizationCode, RefreshToken
from mcp.shared.auth import OAuthClientInformationFull

from glossogen.server.mcp.oauth_records import (
    AccessTokenWithGroup,
    AuthorizationCodeWithGroup,
    PendingConsentRequest,
    RefreshTokenWithGroup,
)
from glossogen.server.mcp.oauth_storage import PENDING_CONSENT_LIFETIME

logger = logging.getLogger(__name__)


class _PendingConsentEntry:
    """A parked consent request plus its absolute expiry epoch (seconds)."""

    def __init__(self, request: PendingConsentRequest, expires_at: float) -> None:
        self.request = request
        self.expires_at = expires_at


class InMemoryOAuthStorage:
    """Process-local OAuth storage; satisfies ``OAuthStoragePort`` structurally."""

    def __init__(self) -> None:
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthorizationCodeWithGroup] = {}
        self._access_tokens: dict[str, AccessTokenWithGroup] = {}
        self._refresh_tokens: dict[str, RefreshTokenWithGroup] = {}
        self._pending_consents: dict[str, _PendingConsentEntry] = {}

    # ------------------------------------------------------------------
    # Clients
    # ------------------------------------------------------------------

    async def save_client(self, client: OAuthClientInformationFull) -> None:
        """Insert or replace a registered OAuth client."""
        if client.client_id is None:
            raise ValueError("Cannot store an OAuth client without a client_id")
        self._clients[client.client_id] = client

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Look up a client by ID. Returns None if not found."""
        return self._clients.get(client_id)

    # ------------------------------------------------------------------
    # Authorization codes
    # ------------------------------------------------------------------

    async def save_authorization_code(self, code: AuthorizationCode, group_id: UUID) -> None:
        """Persist an authorization code bound to ``group_id``."""
        self._auth_codes[code.code] = AuthorizationCodeWithGroup(code=code, group_id=group_id)

    async def load_authorization_code(
        self, client_id: str, code: str
    ) -> AuthorizationCodeWithGroup | None:
        """Load an authorization code (with its group_id), or None if missing/expired."""
        entry = self._auth_codes.get(code)
        if entry is None or entry.code.client_id != client_id:
            return None
        if time.time() > entry.code.expires_at:
            await self.delete_authorization_code(code=code)
            return None
        return entry

    async def delete_authorization_code(self, code: str) -> None:
        """Delete an authorization code (consumed or expired)."""
        self._auth_codes.pop(code, None)

    # ------------------------------------------------------------------
    # Access tokens
    # ------------------------------------------------------------------

    async def save_access_token(self, token: AccessToken, group_id: UUID) -> None:
        """Persist an access token bound to ``group_id``."""
        self._access_tokens[token.token] = AccessTokenWithGroup(token=token, group_id=group_id)

    async def load_access_token(self, token: str) -> AccessTokenWithGroup | None:
        """Load an access token (with its group_id), or None if missing/expired."""
        entry = self._access_tokens.get(token)
        if entry is None:
            return None
        expires_at = entry.token.expires_at
        if expires_at is not None and time.time() > expires_at:
            await self.delete_access_token(token=token)
            return None
        return entry

    async def delete_access_token(self, token: str) -> None:
        """Delete an access token."""
        self._access_tokens.pop(token, None)

    async def delete_access_tokens_for_client(self, client_id: str) -> None:
        """Delete all access tokens for a given client."""
        for token in [t for t, e in self._access_tokens.items() if e.token.client_id == client_id]:
            self._access_tokens.pop(token, None)

    # ------------------------------------------------------------------
    # Refresh tokens
    # ------------------------------------------------------------------

    async def save_refresh_token(self, token: RefreshToken, group_id: UUID) -> None:
        """Persist a refresh token bound to ``group_id``."""
        self._refresh_tokens[token.token] = RefreshTokenWithGroup(token=token, group_id=group_id)

    async def load_refresh_token(self, client_id: str, token: str) -> RefreshTokenWithGroup | None:
        """Load a refresh token (with its group_id), or None if missing/expired."""
        entry = self._refresh_tokens.get(token)
        if entry is None or entry.token.client_id != client_id:
            return None
        expires_at = entry.token.expires_at
        if expires_at is not None and time.time() > expires_at:
            await self.delete_refresh_token(token=token)
            return None
        return entry

    async def delete_refresh_token(self, token: str) -> None:
        """Delete a refresh token."""
        self._refresh_tokens.pop(token, None)

    async def delete_refresh_tokens_for_client(self, client_id: str) -> None:
        """Delete all refresh tokens for a given client."""
        for token in [t for t, e in self._refresh_tokens.items() if e.token.client_id == client_id]:
            self._refresh_tokens.pop(token, None)

    # ------------------------------------------------------------------
    # Pending OAuth consent requests
    # ------------------------------------------------------------------

    async def save_pending_consent(self, request: PendingConsentRequest) -> None:
        """Persist a pending consent request waiting for approval."""
        self._pending_consents[request.request_id] = _PendingConsentEntry(
            request=request,
            expires_at=time.time() + PENDING_CONSENT_LIFETIME,
        )

    async def load_pending_consent(self, request_id: str) -> PendingConsentRequest | None:
        """Load a pending consent request by ID. Returns None if missing or expired."""
        entry = self._pending_consents.get(request_id)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            await self.delete_pending_consent(request_id=request_id)
            return None
        return entry.request

    async def delete_pending_consent(self, request_id: str) -> None:
        """Delete a pending consent request (consumed or expired)."""
        self._pending_consents.pop(request_id, None)
