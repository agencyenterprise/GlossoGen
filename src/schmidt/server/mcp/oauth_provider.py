"""OAuth authorization server provider for the Schmidt MCP server.

Implements the ``OAuthAuthorizationServerProvider`` protocol from the MCP
library, backed by :class:`OAuthStorage` for persistence. Delegates user
authentication to :mod:`oauth_login_page` which serves a password form when
``APP_PASSWORD`` is configured, or auto-approves when auth is disabled.
"""

import logging
import time

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from schmidt.server.mcp.oauth_storage import (
    ACCESS_TOKEN_LIFETIME,
    AUTHORIZATION_CODE_LIFETIME,
    REFRESH_TOKEN_LIFETIME,
    OAuthStorage,
)

logger = logging.getLogger(__name__)


class SchmidtOAuthProvider:
    """OAuth provider backed by SQLite storage.

    When ``app_password`` is None the server runs without user authentication
    and the authorize flow auto-approves every request.
    """

    def __init__(self, storage: OAuthStorage, login_url: str, app_password: str | None) -> None:
        self._storage = storage
        self._login_url = login_url
        self._app_password = app_password

    # ------------------------------------------------------------------
    # Client registration
    # ------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Retrieve a registered client by ID."""
        return await self._storage.get_client(client_id=client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Register a new OAuth client with generated credentials."""
        client_info.client_id = OAuthStorage.generate_client_id()
        client_info.client_secret = OAuthStorage.generate_client_secret()
        client_info.client_id_issued_at = int(time.time())
        await self._storage.save_client(client=client_info)
        logger.info("Registered OAuth client %s", client_info.client_id)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Return a URL the user-agent is redirected to for authentication.

        If no ``APP_PASSWORD`` is set the code is issued immediately and the
        user is redirected straight to the client callback. Otherwise we
        redirect to the login page which validates the password first.
        """
        if self._app_password is None:
            return await self._auto_approve(client=client, params=params)
        return self._build_login_redirect(client=client, params=params)

    async def _auto_approve(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Issue an authorization code without user interaction."""
        code = await self._create_authorization_code(client=client, params=params)
        return construct_redirect_uri(
            str(params.redirect_uri),
            code=code.code,
            state=params.state,
        )

    def _build_login_redirect(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Build a URL to the login page carrying all OAuth parameters."""
        scopes_str = " ".join(params.scopes) if params.scopes else ""
        return construct_redirect_uri(
            self._login_url,
            client_id=client.client_id,
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=str(int(params.redirect_uri_provided_explicitly)),
            code_challenge=params.code_challenge,
            state=params.state,
            scope=scopes_str,
            resource=params.resource,
        )

    async def create_authorization_code_for_login(
        self, client_id: str, params: AuthorizationParams
    ) -> AuthorizationCode:
        """Called by the login page after successful password verification.

        Public so that the login route handler can invoke it directly.
        """
        client = await self._storage.get_client(client_id=client_id)
        if client is None:
            raise AuthorizeError(
                error="unauthorized_client",
                error_description="Unknown client",
            )
        return await self._create_authorization_code(client=client, params=params)

    async def _create_authorization_code(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> AuthorizationCode:
        """Generate and persist an authorization code."""
        code = AuthorizationCode(
            code=OAuthStorage.generate_token(),
            client_id=client.client_id or "",
            scopes=params.scopes if params.scopes else [],
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            expires_at=time.time() + AUTHORIZATION_CODE_LIFETIME,
        )
        await self._storage.save_authorization_code(code=code)
        return code

    # ------------------------------------------------------------------
    # Token exchange
    # ------------------------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        """Load a stored authorization code for the given client."""
        return await self._storage.load_authorization_code(
            client_id=client.client_id or "",
            code=authorization_code,
        )

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,  # noqa: ARG002 — protocol-required
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Exchange an authorization code for access + refresh tokens."""
        await self._storage.delete_authorization_code(code=authorization_code.code)

        now = int(time.time())
        access = AccessToken(
            token=OAuthStorage.generate_token(),
            client_id=authorization_code.client_id,
            scopes=authorization_code.scopes,
            resource=authorization_code.resource,
            expires_at=now + ACCESS_TOKEN_LIFETIME,
        )
        refresh = RefreshToken(
            token=OAuthStorage.generate_token(),
            client_id=authorization_code.client_id,
            scopes=authorization_code.scopes,
            expires_at=now + REFRESH_TOKEN_LIFETIME,
        )
        await self._storage.save_access_token(token=access)
        await self._storage.save_refresh_token(token=refresh)

        logger.info(
            "Issued tokens for client %s (scopes=%s)",
            authorization_code.client_id,
            authorization_code.scopes,
        )
        return OAuthToken(
            access_token=access.token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_LIFETIME,
            scope=" ".join(access.scopes),
            refresh_token=refresh.token,
        )

    # ------------------------------------------------------------------
    # Refresh tokens
    # ------------------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        """Load a stored refresh token for the given client."""
        return await self._storage.load_refresh_token(
            client_id=client.client_id or "",
            token=refresh_token,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,  # noqa: ARG002 — protocol-required
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Rotate the refresh token and issue a new access token."""
        await self._storage.delete_refresh_token(token=refresh_token.token)

        effective_scopes = scopes if scopes else refresh_token.scopes
        now = int(time.time())

        access = AccessToken(
            token=OAuthStorage.generate_token(),
            client_id=refresh_token.client_id,
            scopes=effective_scopes,
            expires_at=now + ACCESS_TOKEN_LIFETIME,
        )
        new_refresh = RefreshToken(
            token=OAuthStorage.generate_token(),
            client_id=refresh_token.client_id,
            scopes=effective_scopes,
            expires_at=now + REFRESH_TOKEN_LIFETIME,
        )
        await self._storage.save_access_token(token=access)
        await self._storage.save_refresh_token(token=new_refresh)

        logger.info("Rotated refresh token for client %s", refresh_token.client_id)
        return OAuthToken(
            access_token=access.token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_LIFETIME,
            scope=" ".join(effective_scopes),
            refresh_token=new_refresh.token,
        )

    # ------------------------------------------------------------------
    # Access token verification
    # ------------------------------------------------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Verify and return an access token."""
        return await self._storage.load_access_token(token=token)

    # ------------------------------------------------------------------
    # Revocation
    # ------------------------------------------------------------------

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """Revoke a token and all related tokens for the same client."""
        client_id = token.client_id
        if isinstance(token, AccessToken):
            await self._storage.delete_access_token(token=token.token)
            await self._storage.delete_refresh_tokens_for_client(client_id=client_id)
        else:
            await self._storage.delete_refresh_token(token=token.token)
            await self._storage.delete_access_tokens_for_client(client_id=client_id)
        logger.info("Revoked tokens for client %s", client_id)
