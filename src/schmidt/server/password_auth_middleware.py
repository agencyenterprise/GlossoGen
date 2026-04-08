"""Pure ASGI middleware for shared-password authentication.

Checks every HTTP request for a valid password in either the Authorization
header (Bearer token) or the ``token`` query parameter. Skips CORS preflight
(OPTIONS), the health-check endpoint, the MCP endpoint, and non-HTTP scopes.
"""

import hmac
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


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

        if request.url.path.startswith("/mcp"):
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
