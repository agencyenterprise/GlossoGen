"""OAuth authorization server provider for the glossogen MCP server.

Implements the ``OAuthAuthorizationServerProvider`` protocol from the MCP
library, backed by :class:`OAuthStorage` (Postgres). Every authorization
code, access token, and refresh token is bound to a ``group_id`` at consent
time; the binding is preserved through every exchange and refresh.

Single-tenant mode (no identity provider installed) auto-approves consent and
binds issued tokens to the synthetic ``local`` group. Multi-tenant mode parks the
request as a ``pending_oauth_consents`` row keyed by an opaque
``request_id`` and redirects the browser to
``{FRONTEND_URL}/mcp-consent?request_id=<id>``; the frontend page POSTs
back to ``/mcp/consent/approve`` once the user has signed in and picked
the target group, and that endpoint calls back into
:meth:`approve_pending_consent` to mint the authorization code.
"""

import logging
import time
from collections.abc import Callable
from uuid import UUID

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from glossogen.server.identity.identity_provider import IdentityProvider
from glossogen.server.mcp.oauth_records import PendingConsentRequest
from glossogen.server.mcp.oauth_storage import (
    ACCESS_TOKEN_LIFETIME,
    AUTHORIZATION_CODE_LIFETIME,
    REFRESH_TOKEN_LIFETIME,
    OAuthStorage,
)
from glossogen.server.mcp.oauth_storage_port import OAuthStoragePort

logger = logging.getLogger(__name__)


class GlossoGenOAuthProvider:
    """OAuth provider backed by Postgres storage with per-group token binding.

    With no identity provider installed there is exactly one group to authorize, so a
    code is issued immediately and bound to the synthetic ``local`` group. With one
    installed the user must say which of their groups they mean, so the request is
    parked and the user-agent is sent to the provider's consent page, which finalizes
    the code through :meth:`approve_pending_consent`.
    """

    def __init__(
        self,
        storage: OAuthStoragePort,
        get_local_group_id: Callable[[], UUID],
        identity_provider: IdentityProvider | None,
    ) -> None:
        self._storage = storage
        self._get_local_group_id = get_local_group_id
        self._identity_provider = identity_provider

    # ------------------------------------------------------------------
    # Client registration
    # ------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        """Retrieve a registered client by ID."""
        return await self._storage.get_client(client_id=client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        """Persist a dynamically registered OAuth client.

        The MCP SDK's registration handler has already assigned the
        ``client_id``, the issued-at timestamp, and a ``client_secret``,
        the latter only when ``token_endpoint_auth_method`` is not
        ``"none"``. Public clients (PKCE-only loopback clients such as
        Claude Code) register with ``token_endpoint_auth_method == "none"``
        and therefore carry no secret; persisting ``client_info`` unchanged
        keeps them secret-less so the token endpoint authenticates them via
        PKCE alone instead of rejecting the exchange for a missing
        ``client_secret``.
        """
        await self._storage.save_client(client=client_info)
        logger.info("Registered OAuth client %s", client_info.client_id)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Return a URL the user-agent is redirected to for authentication.

        With no identity provider the code is issued immediately for the local group
        and the user is redirected straight to the client callback. With one, the
        request is parked under a ``request_id`` and the user-agent is sent to the
        provider's consent page, which posts back to the provider's own approval
        endpoint and reaches :meth:`approve_pending_consent`.
        """
        if self._identity_provider is None:
            code = await self._create_authorization_code(
                client=client,
                params=params,
                group_id=self._get_local_group_id(),
            )
            return construct_redirect_uri(
                str(params.redirect_uri),
                code=code.code,
                state=params.state,
            )

        request_id = OAuthStorage.generate_token()
        pending = PendingConsentRequest(
            request_id=request_id,
            client_id=client.client_id or "",
            scopes=params.scopes if params.scopes else [],
            code_challenge=params.code_challenge,
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            state=params.state,
        )
        await self._storage.save_pending_consent(request=pending)
        return self._identity_provider.deferred_consent_url(request_id=request_id)

    async def approve_pending_consent(
        self,
        request_id: str,
        group_id: UUID,
    ) -> str:
        """Materialize an authorization code for a previously parked request.

        Called from the identity provider's approval endpoint once it has verified
        the caller and settled which group they are authorizing. Returns the URL the
        user-agent should be redirected to: the OAuth client's ``redirect_uri`` with
        the code and state appended.
        """
        pending = await self._storage.load_pending_consent(request_id=request_id)
        if pending is None:
            raise AuthorizeError(
                error="access_denied",
                error_description="Consent request expired or already used",
            )
        client = await self._storage.get_client(client_id=pending.client_id)
        if client is None:
            raise AuthorizeError(
                error="access_denied",
                error_description=f"Unknown client {pending.client_id}",
            )
        params = AuthorizationParams(
            state=pending.state,
            scopes=pending.scopes,
            code_challenge=pending.code_challenge,
            redirect_uri=AnyUrl(pending.redirect_uri),
            redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
            resource=pending.resource,
        )
        code = await self._create_authorization_code(
            client=client,
            params=params,
            group_id=group_id,
        )
        await self._storage.delete_pending_consent(request_id=request_id)
        return construct_redirect_uri(
            pending.redirect_uri,
            code=code.code,
            state=pending.state,
        )

    async def _create_authorization_code(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
        group_id: UUID,
    ) -> AuthorizationCode:
        """Generate and persist an authorization code bound to ``group_id``."""
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
        await self._storage.save_authorization_code(code=code, group_id=group_id)
        return code

    # ------------------------------------------------------------------
    # Token exchange
    # ------------------------------------------------------------------

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        """Load a stored authorization code for the given client.

        The MCP library protocol expects just ``AuthorizationCode`` here; the
        ``group_id`` is recovered alongside it during ``exchange_authorization_code``
        via the same SELECT.
        """
        result = await self._storage.load_authorization_code(
            client_id=client.client_id or "",
            code=authorization_code,
        )
        return result.code if result is not None else None

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        """Exchange an authorization code for access + refresh tokens.

        Recovers the ``group_id`` originally bound at consent time and
        propagates it to both the access and refresh token rows.
        """
        with_group = await self._storage.load_authorization_code(
            client_id=client.client_id or "",
            code=authorization_code.code,
        )
        if with_group is None:
            raise AuthorizeError(
                error="access_denied",
                error_description="Authorization code expired or already used",
            )
        group_id = with_group.group_id

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
        await self._storage.save_access_token(token=access, group_id=group_id)
        await self._storage.save_refresh_token(token=refresh, group_id=group_id)

        logger.info(
            "Issued tokens for client %s (scopes=%s, group=%s)",
            authorization_code.client_id,
            authorization_code.scopes,
            group_id,
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
        result = await self._storage.load_refresh_token(
            client_id=client.client_id or "",
            token=refresh_token,
        )
        return result.token if result is not None else None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Rotate the refresh token and issue a new access token."""
        with_group = await self._storage.load_refresh_token(
            client_id=client.client_id or "",
            token=refresh_token.token,
        )
        if with_group is None:
            raise AuthorizeError(
                error="access_denied",
                error_description="Refresh token expired or already rotated",
            )
        group_id = with_group.group_id

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
        await self._storage.save_access_token(token=access, group_id=group_id)
        await self._storage.save_refresh_token(token=new_refresh, group_id=group_id)

        logger.info(
            "Rotated refresh token for client %s (group=%s)", refresh_token.client_id, group_id
        )
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
        """Verify and return an access token (group_id lookup is separate)."""
        result = await self._storage.load_access_token(token=token)
        return result.token if result is not None else None

    async def load_access_token_with_group(self, token: str) -> UUID | None:
        """Return the group_id bound to a valid access token, or None if invalid.

        Used by the MCP ASGI wrapper to populate the per-request ``RunContext``
        contextvar so tool implementations don't need to re-parse the bearer
        header.
        """
        result = await self._storage.load_access_token(token=token)
        return result.group_id if result is not None else None

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
