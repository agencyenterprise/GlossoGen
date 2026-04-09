"""Pure ASGI middleware for shared-password authentication.

Checks every HTTP request for a valid password in either the Authorization
header (Bearer token) or the ``token`` query parameter. Skips CORS preflight
(OPTIONS), the health-check endpoint, non-HTTP scopes, and ``/mcp`` paths
(the MCP server handles its own OAuth-based authentication).
"""

import hmac
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Paths that belong to the MCP OAuth flow and must bypass shared-password auth.
_OAUTH_PATH_PREFIXES = (
    "/mcp",
    "/.well-known/oauth-",
    "/.well-known/openid-configuration",
    "/authorize",
    "/token",
    "/register",
    "/revoke",
)


def _is_mcp_or_oauth_path(path: str) -> bool:
    """Check whether a request path belongs to the MCP or OAuth subsystem."""
    for prefix in _OAUTH_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


class PasswordAuthMiddleware:
    """ASGI middleware that gates access behind a shared password.

    Uses pure ASGI (not BaseHTTPMiddleware) to avoid buffering streaming
    responses, which would break SSE endpoints.
    """

    def __init__(self, app: ASGIApp, password: str) -> None:
        self.app = app
        self.password = password

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Check authentication for HTTP requests, pass through everything else."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)

        if request.method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if request.method == "GET" and request.url.path == "/api/health":
            await self.app(scope, receive, send)
            return

        # Skip /mcp paths and OAuth endpoints — the MCP server handles its
        # own OAuth-based authentication via the MCP library.
        if _is_mcp_or_oauth_path(path=request.url.path):
            await self.app(scope, receive, send)
            return

        if self._is_authenticated(request=request):
            await self.app(scope, receive, send)
            return

        logger.warning("Rejected unauthenticated request: %s %s", request.method, request.url.path)
        response = JSONResponse(
            status_code=401,
            content={"detail": "Invalid or missing password"},
        )
        await response(scope, receive, send)

    def _is_authenticated(self, request: Request) -> bool:
        """Check Authorization header and token query parameter."""
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if hmac.compare_digest(token, self.password):
                return True

        token_param = request.query_params.get("token", "")
        if token_param and hmac.compare_digest(token_param, self.password):
            return True

        return False
