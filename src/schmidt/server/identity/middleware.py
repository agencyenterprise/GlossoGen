"""ASGI middleware that resolves per-request identity and attaches it to scope.

The active group is read from the URL slug (``/api/g/{slug}/...`` or
``/mcp/g/{slug}/...``). The Clerk JWT proves *what the user is allowed to
do* — it must list the URL's slug among the user's organization
memberships — but the URL declares *what they are doing right now*. This
makes a user who belongs to multiple Clerk orgs able to open them in
parallel tabs without `setActive` races.

Three modes:

* **Unauthenticated paths** — health, Clerk webhook, OAuth discovery — pass
  through without an Identity attached.
* **Local mode** (``CLERK_SECRET_KEY`` unset) — every request gets the
  synthetic local Identity regardless of URL.
* **Clerk mode** — verify token, parse the URL slug, assert the user is a
  member of that group, resolve the local Postgres group UUID, attach.

Membership is proven by the standard ``org_slug`` claim — the user's
currently active org. Multi-org users are supported via Clerk's
``organizationSyncOptions`` on the frontend middleware (see
``frontend/src/proxy.ts``): when a user navigates to ``/g/<slug>/...``,
Clerk activates that org server-side before minting the session token,
so ``claims.org_slug`` matches the URL slug for any group the user is a
member of. If they are not a member, Clerk leaves the previously active
org in place and this check returns 403.
"""

import logging
import re
from uuid import UUID

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from schmidt.db.local_tenant import LOCAL_GROUP_SLUG, LOCAL_USER_ID
from schmidt.db.queries import get_group_by_slug
from schmidt.server.identity.clerk_verifier import (
    ClerkSessionClaims,
    InvalidClerkToken,
    verify_clerk_session_token,
)
from schmidt.server.identity.identity_model import Identity
from schmidt.server.identity.settings import IdentitySettings

logger = logging.getLogger(__name__)

_GROUP_SLUG_PATTERN = re.compile(r"^/(?:api|mcp)/g/([a-zA-Z0-9_-]+)(?:/|$)")

_UNAUTHENTICATED_PREFIXES = (
    "/api/clerk/webhook",
    "/.well-known/oauth-",
    "/.well-known/openid-configuration",
    # MCP routes run their own OAuth auth (FastMCP's auth layer + the
    # consent_router's inline Clerk JWT verification), so the identity
    # middleware skips them entirely.
    "/mcp",
)

_UNAUTHENTICATED_EXACT = frozenset(
    {
        "/api/health",
    }
)


def _is_unauthenticated_path(path: str) -> bool:
    """Return True for paths that bypass the identity check entirely."""
    if path in _UNAUTHENTICATED_EXACT:
        return True
    for prefix in _UNAUTHENTICATED_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _extract_group_slug(path: str) -> str | None:
    """Pull ``{slug}`` from ``/api/g/{slug}/...`` or ``/mcp/g/{slug}/...``."""
    match = _GROUP_SLUG_PATTERN.match(path)
    if match is None:
        return None
    return match.group(1)


def _bearer_token(request: Request) -> str | None:
    """Extract a JWT from the ``Authorization: Bearer ...`` header."""
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[len("Bearer ") :].strip()
    if not token:
        return None
    return token


def _unauthorized(scope: Scope, detail: str) -> JSONResponse:
    logger.info("401: %s %s — %s", scope.get("method"), scope.get("path"), detail)
    return JSONResponse(status_code=401, content={"detail": detail})


def _forbidden(scope: Scope, detail: str) -> JSONResponse:
    logger.info("403: %s %s — %s", scope.get("method"), scope.get("path"), detail)
    return JSONResponse(status_code=403, content={"detail": detail})


def _not_found(scope: Scope, detail: str) -> JSONResponse:
    logger.info("404: %s %s — %s", scope.get("method"), scope.get("path"), detail)
    return JSONResponse(status_code=404, content={"detail": detail})


def _is_active_org(claims: ClerkSessionClaims, slug: str) -> bool:
    """Return True when the JWT's active org slug matches ``slug``.

    Multi-org users are handled by Clerk's ``organizationSyncOptions``
    on the frontend middleware, which activates the URL's org before the
    token is minted. If the user is not a member of ``slug``, Clerk
    leaves the previously active org in place and this check returns
    False.
    """
    return claims.org_slug is not None and claims.org_slug == slug


class ClerkIdentityMiddleware:
    """ASGI middleware: verify Clerk token, parse URL slug, attach Identity.

    Designed as pure ASGI (not ``BaseHTTPMiddleware``) so SSE streams pass
    through without buffering. Reads the DB pool and synthetic-local group
    UUID from ``app.state`` at request time (set during FastAPI lifespan
    startup), so the middleware can be added to the app before the pool is
    opened.
    """

    def __init__(self, app: ASGIApp, settings: IdentitySettings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if request.method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if _is_unauthenticated_path(path=request.url.path):
            await self.app(scope, receive, send)
            return

        if self.settings.is_local_mode:
            request.state.identity = self._build_local_identity(request=request)
            await self.app(scope, receive, send)
            return

        response = await self._resolve_clerk_identity(request=request, scope=scope)
        if response is not None:
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _build_local_identity(self, request: Request) -> Identity:
        """Return the synthetic local-mode identity for every request."""
        local_group_id = request.app.state.local_group_id
        return Identity(
            user_id=LOCAL_USER_ID,
            active_group_id=local_group_id,
            active_group_slug=LOCAL_GROUP_SLUG,
            available_group_ids=frozenset({local_group_id}),
            is_local_mode=True,
        )

    async def _resolve_clerk_identity(
        self,
        request: Request,
        scope: Scope,
    ) -> JSONResponse | None:
        """Verify JWT or OAuth Bearer, parse URL slug, attach Identity.

        Tries Clerk JWT first; on verification failure falls back to the
        MCP OAuth access tokens issued via the consent flow. Either path
        ends with an Identity scoped to the URL's group. Returns a
        ``JSONResponse`` on rejection; ``None`` on success.
        """
        if self.settings.clerk_jwt_key is None:
            return _unauthorized(
                scope=scope,
                detail="Server misconfigured: CLERK_JWT_KEY is not set",
            )

        token = _bearer_token(request=request)
        if token is None:
            return _unauthorized(scope=scope, detail="Missing bearer token")

        url_slug = _extract_group_slug(path=request.url.path)
        if url_slug is None:
            return _forbidden(
                scope=scope,
                detail="Authenticated routes must include /g/{group_slug}/ in the path",
            )

        async with request.app.state.db_pool.connection() as conn:
            group = await get_group_by_slug(conn=conn, slug=url_slug)
        if group is None:
            return _not_found(scope=scope, detail=f"Unknown group slug: {url_slug!r}")

        try:
            claims = verify_clerk_session_token(
                token=token,
                clerk_jwt_key=self.settings.clerk_jwt_key,
                authorized_parties=self.settings.clerk_authorized_parties,
            )
        except InvalidClerkToken as clerk_exc:
            oauth_identity = await self._try_oauth_bearer(
                request=request,
                token=token,
                url_slug=url_slug,
                expected_group_id=group.id,
            )
            if oauth_identity is None:
                return _unauthorized(scope=scope, detail=str(clerk_exc))
            request.state.identity = oauth_identity
            return None

        if not _is_active_org(claims=claims, slug=url_slug):
            return _forbidden(
                scope=scope,
                detail=(
                    f"URL slug {url_slug!r} does not match the JWT's "
                    f"active org_slug {claims.org_slug!r} (user_id="
                    f"{claims.user_id!r}). The frontend either failed to "
                    "activate the org before minting the token, or the "
                    "user is not a member of this group."
                ),
            )

        identity = Identity(
            user_id=claims.user_id,
            active_group_id=group.id,
            active_group_slug=group.slug,
            available_group_ids=frozenset({group.id}),
            is_local_mode=False,
        )
        request.state.identity = identity
        return None

    async def _try_oauth_bearer(
        self,
        request: Request,
        token: str,
        url_slug: str,
        expected_group_id: UUID,
    ) -> Identity | None:
        """Look up a Bearer as an MCP OAuth access token.

        Returns an Identity scoped to the URL's group when the token is
        valid AND its bound ``group_id`` matches ``expected_group_id``;
        returns ``None`` on any failure so the caller can surface the
        original Clerk error to the user.
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
            active_group_slug=url_slug,
            available_group_ids=frozenset({expected_group_id}),
            is_local_mode=False,
        )
