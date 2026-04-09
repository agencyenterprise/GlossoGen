"""SQLite-backed async storage for OAuth clients, authorization codes, and tokens.

Uses aiosqlite for non-blocking database access. All token generation uses
``secrets.token_urlsafe`` with 32 bytes (256 bits of entropy).
"""

import json
import logging
import secrets
import time
from pathlib import Path

import aiosqlite
from mcp.server.auth.provider import AccessToken, AuthorizationCode, RefreshToken
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl

logger = logging.getLogger(__name__)

_TOKEN_BYTES = 32
_CLIENT_ID_BYTES = 16
_CLIENT_SECRET_BYTES = 32

# Default lifetimes in seconds.
ACCESS_TOKEN_LIFETIME = 3600  # 1 hour
REFRESH_TOKEN_LIFETIME = 30 * 24 * 3600  # 30 days
AUTHORIZATION_CODE_LIFETIME = 600  # 10 minutes


class OAuthStorage:
    """Async SQLite storage for OAuth entities."""

    def __init__(self) -> None:
        self._db: aiosqlite.Connection | None = None

    async def initialize(self, db_path: Path) -> None:
        """Open the database connection and create tables."""
        self._db = await aiosqlite.connect(str(db_path))
        await self._db.executescript(_SCHEMA)
        logger.info("OAuth storage initialized at %s", db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("OAuthStorage not initialized — call initialize() first")
        return self._db

    # ------------------------------------------------------------------
    # Clients
    # ------------------------------------------------------------------

    async def save_client(self, client: OAuthClientInformationFull) -> None:
        """Insert or replace a registered OAuth client."""
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO oauth_clients
                (client_id, client_secret, metadata_json, issued_at, secret_expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                client.client_id,
                client.client_secret,
                client.model_dump_json(),
                client.client_id_issued_at,
                client.client_secret_expires_at,
            ),
        )
        await self._conn.commit()

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Look up a client by ID. Returns None if not found."""
        cursor = await self._conn.execute(
            "SELECT metadata_json FROM oauth_clients WHERE client_id = ?",
            (client_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate_json(row[0])

    # ------------------------------------------------------------------
    # Authorization codes
    # ------------------------------------------------------------------

    async def save_authorization_code(self, code: AuthorizationCode) -> None:
        """Persist an authorization code."""
        await self._conn.execute(
            """
            INSERT INTO authorization_codes
                (code, client_id, scopes, code_challenge, redirect_uri,
                 redirect_uri_provided_explicitly, resource, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code.code,
                code.client_id,
                json.dumps(code.scopes),
                code.code_challenge,
                str(code.redirect_uri),
                int(code.redirect_uri_provided_explicitly),
                code.resource,
                code.expires_at,
            ),
        )
        await self._conn.commit()

    async def load_authorization_code(self, client_id: str, code: str) -> AuthorizationCode | None:
        """Load an authorization code, returning None if missing or expired."""
        cursor = await self._conn.execute(
            """
            SELECT code, client_id, scopes, code_challenge, redirect_uri,
                   redirect_uri_provided_explicitly, resource, expires_at
            FROM authorization_codes
            WHERE code = ? AND client_id = ?
            """,
            (code, client_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        expires_at = row[7]
        if time.time() > expires_at:
            await self.delete_authorization_code(code=code)
            return None
        return AuthorizationCode(
            code=row[0],
            client_id=row[1],
            scopes=json.loads(row[2]),
            code_challenge=row[3],
            redirect_uri=AnyUrl(row[4]),
            redirect_uri_provided_explicitly=bool(row[5]),
            resource=row[6],
            expires_at=row[7],
        )

    async def delete_authorization_code(self, code: str) -> None:
        """Delete an authorization code (consumed or expired)."""
        await self._conn.execute("DELETE FROM authorization_codes WHERE code = ?", (code,))
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Access tokens
    # ------------------------------------------------------------------

    async def save_access_token(self, token: AccessToken) -> None:
        """Persist an access token."""
        await self._conn.execute(
            """
            INSERT INTO access_tokens (token, client_id, scopes, resource, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                token.token,
                token.client_id,
                json.dumps(token.scopes),
                token.resource,
                token.expires_at,
            ),
        )
        await self._conn.commit()

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Load an access token, returning None if missing or expired."""
        cursor = await self._conn.execute(
            "SELECT token, client_id, scopes, resource, expires_at"
            " FROM access_tokens WHERE token = ?",
            (token,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        expires_at = row[4]
        if expires_at is not None and time.time() > expires_at:
            await self.delete_access_token(token=token)
            return None
        return AccessToken(
            token=row[0],
            client_id=row[1],
            scopes=json.loads(row[2]),
            resource=row[3],
            expires_at=row[4],
        )

    async def delete_access_token(self, token: str) -> None:
        """Delete an access token."""
        await self._conn.execute("DELETE FROM access_tokens WHERE token = ?", (token,))
        await self._conn.commit()

    async def delete_access_tokens_for_client(self, client_id: str) -> None:
        """Delete all access tokens for a given client."""
        await self._conn.execute("DELETE FROM access_tokens WHERE client_id = ?", (client_id,))
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Refresh tokens
    # ------------------------------------------------------------------

    async def save_refresh_token(self, token: RefreshToken) -> None:
        """Persist a refresh token."""
        await self._conn.execute(
            """
            INSERT INTO refresh_tokens (token, client_id, scopes, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                token.token,
                token.client_id,
                json.dumps(token.scopes),
                token.expires_at,
            ),
        )
        await self._conn.commit()

    async def load_refresh_token(self, client_id: str, token: str) -> RefreshToken | None:
        """Load a refresh token, returning None if missing or expired."""
        cursor = await self._conn.execute(
            "SELECT token, client_id, scopes, expires_at"
            " FROM refresh_tokens WHERE token = ? AND client_id = ?",
            (token, client_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        expires_at = row[3]
        if expires_at is not None and time.time() > expires_at:
            await self.delete_refresh_token(token=token)
            return None
        return RefreshToken(
            token=row[0],
            client_id=row[1],
            scopes=json.loads(row[2]),
            expires_at=row[3],
        )

    async def delete_refresh_token(self, token: str) -> None:
        """Delete a refresh token."""
        await self._conn.execute("DELETE FROM refresh_tokens WHERE token = ?", (token,))
        await self._conn.commit()

    async def delete_refresh_tokens_for_client(self, client_id: str) -> None:
        """Delete all refresh tokens for a given client."""
        await self._conn.execute("DELETE FROM refresh_tokens WHERE client_id = ?", (client_id,))
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def purge_expired(self) -> int:
        """Delete all expired tokens and codes. Returns the number of rows deleted."""
        now = time.time()
        total = 0
        for table in ("authorization_codes", "access_tokens", "refresh_tokens"):
            cursor = await self._conn.execute(
                f"DELETE FROM {table} WHERE expires_at IS NOT NULL AND expires_at < ?",  # noqa: S608
                (now,),
            )
            total += cursor.rowcount
        await self._conn.commit()
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


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id          TEXT PRIMARY KEY,
    client_secret      TEXT,
    metadata_json      TEXT NOT NULL,
    issued_at          INTEGER,
    secret_expires_at  INTEGER
);

CREATE TABLE IF NOT EXISTS authorization_codes (
    code                            TEXT PRIMARY KEY,
    client_id                       TEXT NOT NULL,
    scopes                          TEXT NOT NULL,
    code_challenge                  TEXT NOT NULL,
    redirect_uri                    TEXT NOT NULL,
    redirect_uri_provided_explicitly INTEGER NOT NULL,
    resource                        TEXT,
    expires_at                      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS access_tokens (
    token       TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL,
    scopes      TEXT NOT NULL,
    resource    TEXT,
    expires_at  INTEGER
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    token       TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL,
    scopes      TEXT NOT NULL,
    expires_at  INTEGER
);
"""
