"""Mounting of the MCP server, its OAuth provider, and the OAuth discovery routes.

Everything here is conditional on ``OAUTH_ISSUER_URL``. When it is unset the MCP
endpoint is not mounted at all, and :class:`StubSessionManager` stands in for the
session manager the application's lifespan starts.
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from glossogen.db.pool import get_database_url
from glossogen.server.identity.identity_provider import IdentityProvider
from glossogen.server.mcp.browser import mount_mcp_browser
from glossogen.server.mcp.in_memory_oauth_storage import InMemoryOAuthStorage
from glossogen.server.mcp.oauth_provider import GlossoGenOAuthProvider
from glossogen.server.mcp.oauth_storage import OAuthStorage
from glossogen.server.mcp.oauth_storage_port import OAuthStoragePort
from glossogen.server.mcp.whoami_router import router as whoami_router

logger = logging.getLogger(__name__)


class _NoOpSessionContext:
    """Async context manager that starts and stops nothing."""

    async def __aenter__(self) -> None:
        pass

    async def __aexit__(self, *_args: object) -> None:
        pass


class StubSessionManager:
    """Stands in for the MCP session manager when MCP is disabled.

    The application's lifespan always enters ``mcp_session_manager.run()``, so
    something has to be there when ``OAUTH_ISSUER_URL`` is unset.
    """

    def run(self) -> _NoOpSessionContext:
        """Return a no-op async context manager."""
        return _NoOpSessionContext()


def _build_oauth_storage(app: FastAPI) -> OAuthStoragePort:
    """Pick the OAuth storage backend for this process.

    Postgres when ``DATABASE_URL`` is set, otherwise in-memory. The Postgres
    variant reads the pool through a lazy getter because it is constructed
    before the lifespan opens the pool.
    """
    if get_database_url() is None:
        return InMemoryOAuthStorage()
    return OAuthStorage(get_pool=lambda: app.state.db_pool)


def _add_oauth_discovery_routes(app: FastAPI, mcp_issuer_url: str) -> None:
    """Serve the OAuth discovery documents at the host root.

    RFC 9728 and RFC 8414 place these at the root with the resource path
    appended. The MCP library serves them inside the sub-app at ``/mcp``, so
    they are proxied here. Inserted at position 0 so the mounted sub-app cannot
    shadow them.
    """
    resource_metadata = {
        "resource": mcp_issuer_url,
        "authorization_servers": [mcp_issuer_url],
        "scopes_supported": ["read", "write"],
        "bearer_methods_supported": ["header"],
    }
    authorization_server_metadata = {
        "issuer": mcp_issuer_url,
        "authorization_endpoint": f"{mcp_issuer_url}/authorize",
        "token_endpoint": f"{mcp_issuer_url}/token",
        "registration_endpoint": f"{mcp_issuer_url}/register",
        "scopes_supported": ["read", "write"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
        ],
        "code_challenge_methods_supported": ["S256"],
        "revocation_endpoint": f"{mcp_issuer_url}/revoke",
    }

    async def serve_resource_metadata(_request: Request) -> Response:
        return JSONResponse(content=resource_metadata)

    async def serve_authorization_server_metadata(_request: Request) -> Response:
        return JSONResponse(content=authorization_server_metadata)

    for path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
    ):
        app.routes.insert(0, Route(path, endpoint=serve_resource_metadata, methods=["GET"]))
    for path in (
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-authorization-server/mcp",
    ):
        app.routes.insert(
            0,
            Route(path, endpoint=serve_authorization_server_metadata, methods=["GET"]),
        )


def mount_oauth_and_mcp(
    app: FastAPI,
    runs_dir: Path,
    oauth_issuer_url: str,
    identity_provider: IdentityProvider | None,
) -> None:
    """Mount the MCP endpoint with OAuth, recording both on ``app.state``.

    Sets ``app.state.oauth_storage``, ``app.state.oauth_provider`` and
    ``app.state.mcp_session_manager``. The provider reads the local group's UUID
    through a lazy getter because the lifespan resolves it after this runs.
    """
    logger.info("OAuth enabled (issuer=%s)", oauth_issuer_url)
    storage = _build_oauth_storage(app=app)
    mcp_issuer_url = f"{oauth_issuer_url}/mcp"
    oauth_provider = GlossoGenOAuthProvider(
        storage=storage,
        get_local_group_id=lambda: app.state.local_group_id,
        identity_provider=identity_provider,
    )
    app.state.oauth_storage = storage
    app.state.oauth_provider = oauth_provider
    app.include_router(whoami_router)
    mount_mcp_browser(
        app=app,
        runs_dir=runs_dir,
        oauth_provider=oauth_provider,
        issuer_url=mcp_issuer_url,
    )
    _add_oauth_discovery_routes(app=app, mcp_issuer_url=mcp_issuer_url)
