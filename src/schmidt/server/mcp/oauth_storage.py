"""Postgres-backed storage for OAuth clients, authorization codes, and tokens.

Uses ``psycopg3`` async via the shared connection pool on
``app.state.db_pool``. Every issued authorization code, access token, and
refresh token carries the ``group_id`` chosen at consent time, so an MCP tool
call authenticated by a token is automatically scoped to that group's runs.
All token generation uses ``secrets.token_urlsafe`` with 32 bytes.
"""

import json
import logging
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from mcp.server.auth.provider import AccessToken, AuthorizationCode, RefreshToken
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

from schmidt.db.pool import DbPool
from schmidt.server.mcp.oauth_records import (
    AccessTokenWithGroup,
    AuthorizationCodeWithGroup,
    PendingConsentRequest,
    RefreshTokenWithGroup,
)

logger = logging.getLogger(__name__)

_TOKEN_BYTES = 32
_CLIENT_ID_BYTES = 16
_CLIENT_SECRET_BYTES = 32

# Default lifetimes in seconds.
ACCESS_TOKEN_LIFETIME = 3600  # 1 hour
REFRESH_TOKEN_LIFETIME = 30 * 24 * 3600  # 30 days
AUTHORIZATION_CODE_LIFETIME = 600  # 10 minutes
PENDING_CONSENT_LIFETIME = 600  # 10 minutes


class OAuthStorage:
    """Postgres-backed storage for OAuth entities, with per-token group scoping."""

    def __init__(self, get_pool: Callable[[], DbPool]) -> None:
        self._get_pool = get_pool

    @property
    def _pool(self) -> DbPool:
        return self._get_pool()

    # ------------------------------------------------------------------
    # Clients
    # ------------------------------------------------------------------

    async def save_client(self, client: OAuthClientInformationFull) -> None:
        """Insert or replace a registered OAuth client."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO oauth_clients
                    (client_id, client_secret, metadata_json, issued_at, secret_expires_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (client_id) DO UPDATE
                  SET client_secret = EXCLUDED.client_secret,
                      metadata_json = EXCLUDED.metadata_json,
                      issued_at = EXCLUDED.issued_at,
                      secret_expires_at = EXCLUDED.secret_expires_at
                """,
                (
                    client.client_id,
                    client.client_secret,
                    client.model_dump_json(),
                    client.client_id_issued_at,
                    client.client_secret_expires_at,
                ),
            )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Look up a client by ID. Returns None if not found."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT metadata_json FROM oauth_clients WHERE client_id = %s",
                (client_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate_json(row[0])

    # ------------------------------------------------------------------
    # Authorization codes
    # ------------------------------------------------------------------

    async def save_authorization_code(self, code: AuthorizationCode, group_id: UUID) -> None:
        """Persist an authorization code bound to ``group_id``."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO authorization_codes
                    (code, client_id, group_id, scopes, code_challenge, redirect_uri,
                     redirect_uri_provided_explicitly, resource, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    code.code,
                    code.client_id,
                    group_id,
                    json.dumps(code.scopes),
                    code.code_challenge,
                    str(code.redirect_uri),
                    code.redirect_uri_provided_explicitly,
                    code.resource,
                    _epoch_to_dt(code.expires_at),
                ),
            )

    async def load_authorization_code(
        self,
        client_id: str,
        code: str,
    ) -> AuthorizationCodeWithGroup | None:
        """Load an authorization code (with its group_id), or None if missing/expired."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT code, client_id, group_id, scopes, code_challenge, redirect_uri,
                       redirect_uri_provided_explicitly, resource, expires_at
                FROM authorization_codes
                WHERE code = %s AND client_id = %s
                """,
                (code, client_id),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        expires_at: datetime = row[8]
        if datetime.now(tz=UTC) > expires_at:
            await self.delete_authorization_code(code=code)
            return None
        auth_code = AuthorizationCode(
            code=row[0],
            client_id=row[1],
            scopes=json.loads(row[3]),
            code_challenge=row[4],
            redirect_uri=AnyUrl(row[5]),
            redirect_uri_provided_explicitly=bool(row[6]),
            resource=row[7],
            expires_at=expires_at.timestamp(),
        )
        return AuthorizationCodeWithGroup(code=auth_code, group_id=row[2])

    async def delete_authorization_code(self, code: str) -> None:
        """Delete an authorization code (consumed or expired)."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM authorization_codes WHERE code = %s", (code,))

    # ------------------------------------------------------------------
    # Access tokens
    # ------------------------------------------------------------------

    async def save_access_token(self, token: AccessToken, group_id: UUID) -> None:
        """Persist an access token bound to ``group_id``."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO access_tokens (token, client_id, group_id, scopes, resource, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    token.token,
                    token.client_id,
                    group_id,
                    json.dumps(token.scopes),
                    token.resource,
                    _epoch_to_dt(token.expires_at),
                ),
            )

    async def load_access_token(self, token: str) -> AccessTokenWithGroup | None:
        """Load an access token (with its group_id), or None if missing/expired."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT token, client_id, group_id, scopes, resource, expires_at
                FROM access_tokens WHERE token = %s
                """,
                (token,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        expires_at: datetime | None = row[5]
        if expires_at is not None and datetime.now(tz=UTC) > expires_at:
            await self.delete_access_token(token=token)
            return None
        access = AccessToken(
            token=row[0],
            client_id=row[1],
            scopes=json.loads(row[3]),
            resource=row[4],
            expires_at=int(expires_at.timestamp()) if expires_at is not None else None,
        )
        return AccessTokenWithGroup(token=access, group_id=row[2])

    async def delete_access_token(self, token: str) -> None:
        """Delete an access token."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM access_tokens WHERE token = %s", (token,))

    async def delete_access_tokens_for_client(self, client_id: str) -> None:
        """Delete all access tokens for a given client."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM access_tokens WHERE client_id = %s", (client_id,))

    # ------------------------------------------------------------------
    # Refresh tokens
    # ------------------------------------------------------------------

    async def save_refresh_token(self, token: RefreshToken, group_id: UUID) -> None:
        """Persist a refresh token bound to ``group_id``."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO refresh_tokens (token, client_id, group_id, scopes, expires_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    token.token,
                    token.client_id,
                    group_id,
                    json.dumps(token.scopes),
                    _epoch_to_dt(token.expires_at),
                ),
            )

    async def load_refresh_token(
        self,
        client_id: str,
        token: str,
    ) -> RefreshTokenWithGroup | None:
        """Load a refresh token (with its group_id), or None if missing/expired."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT token, client_id, group_id, scopes, expires_at
                FROM refresh_tokens WHERE token = %s AND client_id = %s
                """,
                (token, client_id),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        expires_at: datetime | None = row[4]
        if expires_at is not None and datetime.now(tz=UTC) > expires_at:
            await self.delete_refresh_token(token=token)
            return None
        refresh = RefreshToken(
            token=row[0],
            client_id=row[1],
            scopes=json.loads(row[3]),
            expires_at=int(expires_at.timestamp()) if expires_at is not None else None,
        )
        return RefreshTokenWithGroup(token=refresh, group_id=row[2])

    async def delete_refresh_token(self, token: str) -> None:
        """Delete a refresh token."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM refresh_tokens WHERE token = %s", (token,))

    async def delete_refresh_tokens_for_client(self, client_id: str) -> None:
        """Delete all refresh tokens for a given client."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM refresh_tokens WHERE client_id = %s", (client_id,))

    # ------------------------------------------------------------------
    # Pending OAuth consent requests (Clerk-gated approval)
    # ------------------------------------------------------------------

    async def save_pending_consent(self, request: PendingConsentRequest) -> None:
        """Persist a pending consent request waiting for Clerk-gated approval."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO pending_oauth_consents
                    (request_id, client_id, scopes, code_challenge, redirect_uri,
                     redirect_uri_provided_explicitly, resource, state, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    request.request_id,
                    request.client_id,
                    json.dumps(request.scopes),
                    request.code_challenge,
                    request.redirect_uri,
                    request.redirect_uri_provided_explicitly,
                    request.resource,
                    request.state,
                    datetime.now(tz=UTC) + timedelta(seconds=PENDING_CONSENT_LIFETIME),
                ),
            )

    async def load_pending_consent(self, request_id: str) -> PendingConsentRequest | None:
        """Load a pending consent request by ID. Returns None if missing or expired."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                """
                SELECT request_id, client_id, scopes, code_challenge, redirect_uri,
                       redirect_uri_provided_explicitly, resource, state, expires_at
                FROM pending_oauth_consents WHERE request_id = %s
                """,
                (request_id,),
            )
            row = await cur.fetchone()
        if row is None:
            return None
        expires_at: datetime = row[8]
        if datetime.now(tz=UTC) > expires_at:
            await self.delete_pending_consent(request_id=request_id)
            return None
        return PendingConsentRequest(
            request_id=row[0],
            client_id=row[1],
            scopes=json.loads(row[2]),
            code_challenge=row[3],
            redirect_uri=row[4],
            redirect_uri_provided_explicitly=bool(row[5]),
            resource=row[6],
            state=row[7],
        )

    async def delete_pending_consent(self, request_id: str) -> None:
        """Delete a pending consent request (consumed or expired)."""
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM pending_oauth_consents WHERE request_id = %s",
                (request_id,),
            )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def purge_expired(self) -> int:
        """Delete all expired tokens, codes, and pending consents.

        Returns the number of rows deleted.
        """
        total = 0
        async with self._pool.connection() as conn, conn.cursor() as cur:
            for table in (
                "authorization_codes",
                "access_tokens",
                "refresh_tokens",
                "pending_oauth_consents",
            ):
                await cur.execute(
                    f"DELETE FROM {table} WHERE expires_at IS NOT NULL AND expires_at < NOW()"  # noqa: S608
                )
                total += cur.rowcount
        if total > 0:
            logger.info("Purged %d expired OAuth rows", total)
        return total

    # ------------------------------------------------------------------
    # Token generation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def generate_token() -> str:
        """Generate a cryptographically random token string."""
        return secrets.token_urlsafe(_TOKEN_BYTES)

    @staticmethod
    def generate_client_id() -> str:
        """Generate a random client ID."""
        return secrets.token_urlsafe(_CLIENT_ID_BYTES)

    @staticmethod
    def generate_client_secret() -> str:
        """Generate a random client secret."""
        return secrets.token_urlsafe(_CLIENT_SECRET_BYTES)


def _epoch_to_dt(epoch: float | int | None) -> datetime | None:
    """Convert a unix epoch (seconds) to a timezone-aware ``datetime``."""
    if epoch is None:
        return None
    return datetime.fromtimestamp(0, tz=UTC) + timedelta(seconds=float(epoch))
