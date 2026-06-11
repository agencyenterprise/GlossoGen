"""FastAPI application definition with CORS middleware and route registration."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from schmidt.db.local_tenant import LOCAL_GROUP_ID
from schmidt.db.pool import close_pool, create_pool, get_database_url
from schmidt.server.error_logging_handlers import register_error_logging_handlers
from schmidt.server.identity.bootstrap import ensure_local_group
from schmidt.server.identity.middleware import ClerkIdentityMiddleware
from schmidt.server.identity.settings import load_identity_settings
from schmidt.server.identity.webhook_router import router as clerk_webhook_router
from schmidt.server.mcp.browser import mount_mcp_browser
from schmidt.server.mcp.consent_router import router as mcp_consent_router
from schmidt.server.mcp.in_memory_oauth_storage import InMemoryOAuthStorage
from schmidt.server.mcp.oauth_provider import SchmidtOAuthProvider
from schmidt.server.mcp.oauth_storage import OAuthStorage
from schmidt.server.mcp.oauth_storage_port import OAuthStoragePort
from schmidt.server.pdf.router import router as pdf_export_router
from schmidt.server.response_models import HealthResponse, HealthStatus
from schmidt.server.runs.bundle_router import router as bundle_router
from schmidt.server.runs.router import router as runs_router
from schmidt.server.scenarios.router import router as scenarios_router

load_dotenv()

logger = logging.getLogger(__name__)

_oauth_issuer_url = os.environ.get("OAUTH_ISSUER_URL")
_runs_dir = Path(os.environ.get("SCHMIDT_RUNS_DIR", "./runs"))
_identity_settings = load_identity_settings()


def _resolve_frontend_url() -> str:
    """Pick the frontend base URL used for OAuth consent redirects.

    Reads ``FRONTEND_URL`` directly, then falls back to the first entry of
    ``ALLOWED_ORIGINS``, then to the local-dev default ``http://localhost:3000``.
    """
    explicit = os.environ.get("FRONTEND_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    origins_raw = os.environ.get("ALLOWED_ORIGINS", "")
    for candidate in origins_raw.split(","):
        cleaned = candidate.strip()
        if cleaned:
            return cleaned.rstrip("/")
    return "http://localhost:3000"


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
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Store the configured runs directory, open the DB pool, and start MCP."""
    app.state.runs_dir = _runs_dir
    _runs_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Serving runs from: %s", _runs_dir)

    db_pool = await create_pool(database_url=get_database_url(), min_size=1, max_size=10)
    app.state.db_pool = db_pool
    if db_pool is None:
        if not _identity_settings.is_local_mode:
            raise RuntimeError(
                "DATABASE_URL is unset but CLERK_SECRET_KEY is set. Clerk "
                "multi-tenant auth requires Postgres; set DATABASE_URL, or unset "
                "CLERK_SECRET_KEY to run in no-database local mode."
            )
        app.state.local_group_id = LOCAL_GROUP_ID
        logger.info("Running without a database (no-DB local mode)")
    else:
        app.state.local_group_id = await ensure_local_group(pool=db_pool)
    app.state.identity_settings = _identity_settings
    if _identity_settings.is_local_mode:
        logger.info("Running in local mode (CLERK_SECRET_KEY unset)")
    else:
        logger.info("Running with Clerk authentication")

    if _oauth_issuer_url is not None:
        logger.info("OAuth enabled (issuer=%s)", _oauth_issuer_url)

    async with app.state.mcp_session_manager.run():
        yield

    await close_pool(db_pool)


app = FastAPI(title="Schmidt Simulation Server", lifespan=lifespan)

register_error_logging_handlers(app=app)

app.add_middleware(ClerkIdentityMiddleware, settings=_identity_settings)

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
app.include_router(pdf_export_router)
app.include_router(bundle_router)
app.include_router(scenarios_router)
app.include_router(clerk_webhook_router)

# MCP server with OAuth. Requires OAUTH_ISSUER_URL to be set. The OAuth
# storage and provider read the DB pool / local group UUID via lazy getters
# so they survive being constructed at module load before lifespan runs.
_oauth_storage: OAuthStoragePort | None = None
if _oauth_issuer_url is not None:
    if get_database_url() is None:
        _oauth_storage = InMemoryOAuthStorage()
    else:
        _oauth_storage = OAuthStorage(get_pool=lambda: app.state.db_pool)
    _mcp_issuer_url = f"{_oauth_issuer_url}/mcp"
    _frontend_consent_url = f"{_resolve_frontend_url()}/mcp-consent"
    _oauth_provider = SchmidtOAuthProvider(
        storage=_oauth_storage,
        get_local_group_id=lambda: app.state.local_group_id,
        is_local_mode=_identity_settings.is_local_mode,
        frontend_consent_url=_frontend_consent_url,
    )
    app.state.oauth_provider = _oauth_provider
    app.include_router(mcp_consent_router)

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
