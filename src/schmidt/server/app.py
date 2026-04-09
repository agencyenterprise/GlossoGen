"""FastAPI application definition with CORS middleware and route registration."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from schmidt.server.mcp.browser import mount_mcp_browser
from schmidt.server.mcp.oauth_login_page import create_login_routes
from schmidt.server.mcp.oauth_provider import SchmidtOAuthProvider
from schmidt.server.mcp.oauth_storage import OAuthStorage
from schmidt.server.password_auth_middleware import PasswordAuthMiddleware
from schmidt.server.pdf.router import router as pdf_export_router
from schmidt.server.response_models import AuthVerifyResponse, HealthResponse, HealthStatus
from schmidt.server.runs.artifact_router import router as artifact_export_router
from schmidt.server.runs.fork_router import router as fork_router
from schmidt.server.runs.router import router as runs_router
from schmidt.server.scenarios.router import router as scenarios_router

load_dotenv()

logger = logging.getLogger(__name__)

_app_password = os.environ.get("APP_PASSWORD")
_oauth_issuer_url = os.environ.get("OAUTH_ISSUER_URL")
_runs_dir = Path(os.environ.get("SCHMIDT_RUNS_DIR", "./runs"))


class _StubSessionManager:
    """No-op session manager used when MCP is disabled."""

    class _NoOpCtx:
        async def __aenter__(self) -> None:
            pass

        async def __aexit__(self, *_args: object) -> None:
            pass

    def run(self) -> "_StubSessionManager._NoOpCtx":
        """Return a no-op async context manager."""
        return self._NoOpCtx()


def _parse_allowed_origins() -> list[str]:
    """Read CORS origins from ALLOWED_ORIGINS env var (comma-separated)."""
    origins_raw = os.environ.get("ALLOWED_ORIGINS", "")
    if origins_raw:
        return [origin.strip() for origin in origins_raw.split(",")]
    return ["http://localhost:3000"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Store the configured runs directory, init OAuth storage, and start MCP."""
    app.state.runs_dir = _runs_dir
    _runs_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Serving runs from: %s", _runs_dir)

    # Initialize OAuth storage.
    if _oauth_storage is not None:
        db_path = _runs_dir / "oauth.db"
        await _oauth_storage.initialize(db_path=db_path)
        logger.info("OAuth enabled (issuer=%s)", _oauth_issuer_url)

    async with app.state.mcp_session_manager.run():
        yield

    if _oauth_storage is not None:
        await _oauth_storage.close()


app = FastAPI(title="Schmidt Simulation Server", lifespan=lifespan)

if _app_password:
    app.add_middleware(PasswordAuthMiddleware, password=_app_password)

# CORS must be added last so it is the outermost middleware. This ensures
# CORS headers are present on all responses, including 401s from the auth
# middleware. (FastAPI applies middleware in reverse add order.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router)
app.include_router(fork_router)
app.include_router(pdf_export_router)
app.include_router(artifact_export_router)
app.include_router(scenarios_router)

# MCP server with OAuth. Requires OAUTH_ISSUER_URL to be set.
_oauth_storage: OAuthStorage | None = None
if _oauth_issuer_url is not None:
    _oauth_storage = OAuthStorage()
    _mcp_issuer_url = f"{_oauth_issuer_url}/mcp"
    _login_url = f"{_oauth_issuer_url}/mcp/oauth/login"
    _oauth_provider = SchmidtOAuthProvider(
        storage=_oauth_storage,
        login_url=_login_url,
        app_password=_app_password,
    )
    app.state.oauth_provider = _oauth_provider

    for route in create_login_routes():
        app.routes.insert(0, route)

    mount_mcp_browser(
        app=app,
        runs_dir=_runs_dir,
        oauth_provider=_oauth_provider,
        issuer_url=_mcp_issuer_url,
    )

    # RFC 9728 / RFC 8414: OAuth discovery endpoints must be at the host
    # root level (with the resource path appended). The MCP library serves
    # them inside the sub-app at /mcp, so we proxy them at the root.
    _resource_metadata = {
        "resource": _mcp_issuer_url,
        "authorization_servers": [_mcp_issuer_url],
        "scopes_supported": ["read", "write"],
        "bearer_methods_supported": ["header"],
    }
    _as_metadata = {
        "issuer": _mcp_issuer_url,
        "authorization_endpoint": f"{_mcp_issuer_url}/authorize",
        "token_endpoint": f"{_mcp_issuer_url}/token",
        "registration_endpoint": f"{_mcp_issuer_url}/register",
        "scopes_supported": ["read", "write"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
        ],
        "code_challenge_methods_supported": ["S256"],
        "revocation_endpoint": f"{_mcp_issuer_url}/revoke",
    }

    async def _serve_resource_metadata(_request: Request) -> Response:
        return JSONResponse(content=_resource_metadata)

    async def _serve_as_metadata(_request: Request) -> Response:
        return JSONResponse(content=_as_metadata)

    # Protected resource metadata (RFC 9728).
    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    ):
        app.routes.insert(0, Route(path, endpoint=_serve_resource_metadata, methods=["GET"]))
    # Authorization server metadata (RFC 8414).
    for path in (
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-authorization-server/mcp",
    ):
        app.routes.insert(0, Route(path, endpoint=_serve_as_metadata, methods=["GET"]))
else:
    logger.warning(
        "OAUTH_ISSUER_URL not set — MCP server is disabled. "
        "Set OAUTH_ISSUER_URL to enable the MCP endpoint at /mcp."
    )
    # Provide a stub session manager so the lifespan doesn't break.
    app.state.mcp_session_manager = _StubSessionManager()


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status=HealthStatus.OK)


@app.post("/api/auth/verify", response_model=AuthVerifyResponse)
async def verify_auth() -> AuthVerifyResponse:
    """Verify that the provided password is correct.

    If the request reaches this endpoint, the middleware already validated
    the password. Returns authenticated=True unconditionally.
    """
    return AuthVerifyResponse(authenticated=True)
