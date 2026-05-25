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

Membership is read from either:

1. A custom JWT claim ``org_memberships`` (recommended; configure Clerk's
   JWT template to include ``{{user.organization_memberships}}``).
   Required for concurrent multi-org browsing.
2. Fallback: the standard ``org_slug`` claim (active org only). If the URL
   slug matches the active org, the request is accepted; otherwise 403.
"""

import logging
import re

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


def _is_member_of_slug(claims: ClerkSessionClaims, slug: str) -> bool:
    """Check whether the user proves membership of ``slug`` via JWT claims.

    Accepts either a custom ``org_memberships`` claim (preferred — supports
    multi-org concurrent browsing) or the standard ``org_slug`` claim (the
    user's currently active org).
    """
    for membership in claims.org_memberships:
        if membership.org_slug == slug:
            return True
    if claims.org_slug is not None and claims.org_slug == slug:
        return True
    return False


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
        """Verify JWT, parse URL slug, validate membership, attach Identity.

        Returns a ``JSONResponse`` on rejection; ``None`` on success.
        """
        if self.settings.clerk_jwt_key is None:
            return _unauthorized(
                scope=scope,
                detail="Server misconfigured: CLERK_JWT_KEY is not set",
            )

        token = _bearer_token(request=request)
        if token is None:
            return _unauthorized(scope=scope, detail="Missing bearer token")

        try:
            claims = verify_clerk_session_token(
                token=token,
                clerk_jwt_key=self.settings.clerk_jwt_key,
                authorized_parties=self.settings.clerk_authorized_parties,
            )
        except InvalidClerkToken as exc:
            return _unauthorized(scope=scope, detail=str(exc))

        url_slug = _extract_group_slug(path=request.url.path)
        if url_slug is None:
            return _forbidden(
                scope=scope,
                detail="Authenticated routes must include /g/{group_slug}/ in the path",
            )

        if not _is_member_of_slug(claims=claims, slug=url_slug):
            return _forbidden(
                scope=scope,
                detail=(
                    f"User is not a member of group {url_slug!r}. "
                    "Configure Clerk's JWT template to include "
                    "{{user.organization_memberships}} for multi-org users."
                ),
            )

        async with request.app.state.db_pool.connection() as conn:
            group = await get_group_by_slug(conn=conn, slug=url_slug)
        if group is None:
            return _not_found(scope=scope, detail=f"Unknown group slug: {url_slug!r}")

        identity = Identity(
            user_id=claims.user_id,
            active_group_id=group.id,
            active_group_slug=group.slug,
            available_group_ids=frozenset({group.id}),
            is_local_mode=False,
        )
        request.state.identity = identity
        return None
