"""Protocol describing the OAuth storage surface the provider depends on.

Both the Postgres-backed :class:`~glossogen.server.mcp.oauth_storage.OAuthStorage`
and the :class:`~glossogen.server.mcp.in_memory_oauth_storage.InMemoryOAuthStorage`
(no-database local mode) satisfy this Protocol structurally, so the OAuth
provider can hold either without caring which is in use.
"""

from typing import Protocol
from uuid import UUID

from mcp.server.auth.provider import AccessToken, AuthorizationCode, RefreshToken
from mcp.shared.auth import OAuthClientInformationFull

from glossogen.server.mcp.oauth_records import (
    AccessTokenWithGroup,
    AuthorizationCodeWithGroup,
    PendingConsentRequest,
    RefreshTokenWithGroup,
)


class OAuthStoragePort(Protocol):
    """The set of storage operations the OAuth provider invokes."""

    async def save_client(self, client: OAuthClientInformationFull) -> None: ...

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None: ...

    async def save_authorization_code(self, code: AuthorizationCode, group_id: UUID) -> None: ...

    async def load_authorization_code(
        self, client_id: str, code: str
    ) -> AuthorizationCodeWithGroup | None: ...

    async def delete_authorization_code(self, code: str) -> None: ...

    async def save_access_token(self, token: AccessToken, group_id: UUID) -> None: ...

    async def load_access_token(self, token: str) -> AccessTokenWithGroup | None: ...

    async def delete_access_token(self, token: str) -> None: ...

    async def delete_access_tokens_for_client(self, client_id: str) -> None: ...

    async def save_refresh_token(self, token: RefreshToken, group_id: UUID) -> None: ...

    async def load_refresh_token(
        self, client_id: str, token: str
    ) -> RefreshTokenWithGroup | None: ...

    async def delete_refresh_token(self, token: str) -> None: ...

    async def delete_refresh_tokens_for_client(self, client_id: str) -> None: ...

    async def save_pending_consent(self, request: PendingConsentRequest) -> None: ...

    async def load_pending_consent(self, request_id: str) -> PendingConsentRequest | None: ...

    async def delete_pending_consent(self, request_id: str) -> None: ...
