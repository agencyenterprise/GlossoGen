"""ASGI middleware that resolves per-request identity and attaches it to scope.

The active group is read from the URL slug (``/api/g/{slug}/...`` or
``/mcp/g/{slug}/...``). A credential proves *what the caller is allowed to do*, but
the URL declares *what they are doing right now*. That split is what lets someone
who belongs to several groups open them in parallel tabs without the two requests
fighting over one piece of session state.

Three outcomes:

* **Unauthenticated paths** (health, OAuth discovery, and whatever prefixes the
  installed provider declares) pass through with no Identity attached.
* **No provider installed** is single-tenant mode: every request gets the synthetic
  local Identity regardless of URL.
* **A provider installed** means verify the credential, resolve the URL's slug to a
  ``groups`` row, and ask the provider for an Identity covering that group.

The platform does the slug parsing, the credential extraction and the group lookup
itself, so a provider never queries the ``groups`` table and cannot get tenancy
isolation wrong. See :mod:`glossogen.server.identity.identity_provider`.
"""

import logging
import re
from uuid import UUID

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from glossogen.db.local_tenant import LOCAL_USER_ID
from glossogen.db.queries import get_group_by_slug
from glossogen.server.identity.bearer_credential import bearer_from_header_or_query
from glossogen.server.identity.identity_model import Identity
from glossogen.server.identity.identity_provider import IdentityProvider, IdentityRejected

logger = logging.getLogger(__name__)

_GROUP_SLUG_PATTERN = re.compile(r"^/(?:api|mcp)/g/([a-zA-Z0-9_-]+)(?:/|$)")

_UNAUTHENTICATED_PREFIXES = (
    "/.well-known/oauth-",
    "/.well-known/openid-configuration",
    # MCP routes run their own OAuth auth (FastMCP's auth layer plus the provider's
    # own consent endpoint), so the identity middleware skips them entirely.
    "/mcp",
)

_UNAUTHENTICATED_EXACT = frozenset(
    {
        "/api/health",
        "/api/server-config",
    }
)


def _is_unauthenticated_path(path: str, provider_prefixes: tuple[str, ...]) -> bool:
    """Return True for paths that bypass the identity check entirely."""
    if path in _UNAUTHENTICATED_EXACT:
        return True
    for prefix in _UNAUTHENTICATED_PREFIXES + provider_prefixes:
        if path.startswith(prefix):
            return True
    return False


def _extract_group_slug(path: str) -> str | None:
    """Pull ``{slug}`` from ``/api/g/{slug}/...`` or ``/mcp/g/{slug}/...``."""
    match = _GROUP_SLUG_PATTERN.match(path)
    if match is None:
        return None
    return match.group(1)


def _rejection(scope: Scope, status_code: int, detail: str) -> JSONResponse:
    logger.info("%d: %s %s — %s", status_code, scope.get("method"), scope.get("path"), detail)
    return JSONResponse(status_code=status_code, content={"detail": detail})


class IdentityMiddleware:
    """ASGI middleware: verify a credential, parse the URL slug, attach an Identity.

    Designed as pure ASGI (not ``BaseHTTPMiddleware``) so SSE streams pass through
    without buffering. Reads the DB pool and the synthetic-local group UUID from
    ``app.state`` at request time, since those are set during lifespan startup, after
    the middleware is added.
    """

    def __init__(self, app: ASGIApp, identity_provider: IdentityProvider | None) -> None:
        self.app = app
        self.identity_provider = identity_provider
        if identity_provider is None:
            self.provider_prefixes: tuple[str, ...] = ()
        else:
            self.provider_prefixes = identity_provider.unauthenticated_path_prefixes()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if request.method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if _is_unauthenticated_path(
            path=request.url.path,
            provider_prefixes=self.provider_prefixes,
        ):
            await self.app(scope, receive, send)
            return

        if self.identity_provider is None:
            request.state.identity = self._build_local_identity(request=request)
            await self.app(scope, receive, send)
            return

        response = await self._resolve_identity(request=request, scope=scope)
        if response is not None:
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _build_local_identity(self, request: Request) -> Identity:
        """Return the synthetic single-tenant identity for every request."""
        return Identity(
            user_id=LOCAL_USER_ID,
            active_group_id=request.app.state.local_group_id,
            is_local_mode=True,
        )

    async def _resolve_identity(self, request: Request, scope: Scope) -> JSONResponse | None:
        """Attach an Identity, or return the response that rejects the request.

        Ends with an Identity scoped to the URL's group. Returns ``None`` on success.
        """
        if self.identity_provider is None:
            raise RuntimeError("_resolve_identity called with no identity provider")

        credential = bearer_from_header_or_query(request=request)
        if credential is None:
            return _rejection(scope=scope, status_code=401, detail="Missing bearer token")

        url_slug = _extract_group_slug(path=request.url.path)
        if url_slug is None:
            return _rejection(
                scope=scope,
                status_code=403,
                detail="Authenticated routes must include /g/{group_slug}/ in the path",
            )

        async with request.app.state.db_pool.connection() as conn:
            group = await get_group_by_slug(conn=conn, slug=url_slug)
        if group is None:
            return _rejection(
                scope=scope,
                status_code=404,
                detail=f"Unknown group slug: {url_slug!r}",
            )

        try:
            identity = await self.identity_provider.resolve_identity(
                credential=credential,
                group=group,
            )
        except IdentityRejected as rejected:
            # Tried on any rejection, whatever status the provider chose. An MCP token
            # is not a session credential, so a provider is entitled to reject it with
            # either 401 or 403, and gating this on one of them would make a
            # provider's choice of status code decide whether `glossogen push-to-prod`
            # can reach a hosted backend. The lookup is exact and runs only on an
            # already-failing request, so admitting both costs nothing on the hot path.
            oauth_identity = await self._try_oauth_bearer(
                request=request,
                token=credential,
                expected_group_id=group.id,
            )
            if oauth_identity is None:
                return _rejection(
                    scope=scope,
                    status_code=rejected.status_code,
                    detail=rejected.detail,
                )
            request.state.identity = oauth_identity
            return None

        request.state.identity = identity
        return None

    async def _try_oauth_bearer(
        self,
        request: Request,
        token: str,
        expected_group_id: UUID,
    ) -> Identity | None:
        """Look up a Bearer as an MCP OAuth access token.

        Returns an Identity scoped to the URL's group when the token is valid AND its
        bound ``group_id`` matches ``expected_group_id``; returns ``None`` on any
        failure so the caller can surface the provider's own rejection instead.
        """
        oauth_provider = getattr(request.app.state, "oauth_provider", None)
        if oauth_provider is None:
            return None
        try:
            token_group_id = await oauth_provider.load_access_token_with_group(token=token)
        except Exception:
            logger.exception("OAuth access-token lookup failed")
            return None
        if token_group_id is None or token_group_id != expected_group_id:
            return None
        return Identity(
            user_id=f"oauth:{token[:8]}",
            active_group_id=expected_group_id,
            is_local_mode=False,
        )
