"""Construction of the FastAPI application.

``create_app`` takes its configuration as arguments rather than reading module
globals, so a test can build an app around a different identity configuration and
so the ordering of construction is explicit. ``glossogen.server.app`` calls it
once at module scope to produce the instance uvicorn imports.
"""

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from glossogen.db.local_tenant import LOCAL_GROUP_ID
from glossogen.db.pool import close_pool, create_pool, get_database_url
from glossogen.server.error_logging_handlers import register_error_logging_handlers
from glossogen.server.health_router import router as health_router
from glossogen.server.identity.bootstrap import ensure_local_group
from glossogen.server.identity.identity_provider import IdentityProvider
from glossogen.server.identity.middleware import IdentityMiddleware
from glossogen.server.mcp.oauth_mounting import StubSessionManager, mount_oauth_and_mcp
from glossogen.server.pdf.router import router as pdf_export_router
from glossogen.server.runs.analysis_record_cache import (
    RECORD_CACHE_MAX_RUNS,
    RECORD_CACHE_TTL_SECONDS,
    AnalysisRecordCache,
)
from glossogen.server.runs.analysis_router import router as analysis_router
from glossogen.server.runs.bundle_router import router as bundle_router
from glossogen.server.runs.dashboard_router import router as dashboard_router
from glossogen.server.runs.multi_export_router import router as multi_export_router
from glossogen.server.runs.router import router as runs_router
from glossogen.server.scenarios.router import router as scenarios_router
from glossogen.server.server_runtime_config import ServerRuntimeConfig

logger = logging.getLogger(__name__)

# `@asynccontextmanager` turns the generator function into one returning a
# context manager, which is what FastAPI's `lifespan=` parameter accepts.
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


async def _purge_expired_oauth_rows(app: FastAPI) -> None:
    """Delete OAuth rows that have expired.

    Nothing else deletes them, so the tables only grow. Once per boot is enough:
    these are hour- and month-lived tokens, not a hot path.
    """
    storage = app.state.oauth_storage
    if storage is None:
        return
    try:
        purged = await storage.purge_expired()
    except Exception:
        logger.exception("Could not purge expired OAuth rows; continuing startup")
        return
    if purged:
        logger.info("Purged %d expired OAuth row(s)", purged)


async def _resolve_local_group_id(app: FastAPI, identity_provider: IdentityProvider | None) -> None:
    """Open the database pool and settle which group local mode hands out.

    With no ``DATABASE_URL`` there is no pool, which is only tenable when nothing
    authenticates: the synthetic group falls back to a fixed UUID.
    """
    db_pool = await create_pool(database_url=get_database_url(), min_size=1, max_size=10)
    app.state.db_pool = db_pool
    if db_pool is not None:
        app.state.local_group_id = await ensure_local_group(pool=db_pool)
        return
    if identity_provider is not None:
        raise RuntimeError(
            f"DATABASE_URL is unset but the {identity_provider.provider_name()!r} identity "
            "provider is configured. Multi-tenant auth needs Postgres to resolve a group "
            "slug: set DATABASE_URL, or remove the provider to run in no-database "
            "single-tenant mode."
        )
    app.state.local_group_id = LOCAL_GROUP_ID
    logger.info("Running without a database (no-DB single-tenant mode)")


def _build_lifespan(identity_provider: IdentityProvider | None) -> Lifespan:
    """Build the application lifespan around an explicit identity configuration.

    A closure rather than a module-level function so nothing it needs is read
    from a module global that may not be assigned yet.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Create the runs directory, open the DB pool, and start MCP."""
        runs_dir = app.state.runs_dir
        runs_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Serving runs from: %s", runs_dir)

        await _resolve_local_group_id(app=app, identity_provider=identity_provider)
        if identity_provider is None:
            logger.info("Running in single-tenant mode: no identity provider installed")
        else:
            logger.info("Authenticating with the %r provider", identity_provider.provider_name())

        if not app.state.feature_flags.evaluations_enabled:
            logger.info(
                "Evaluations disabled (ENABLE_EVALUATIONS=false); the REST "
                "evaluate endpoint will reject requests"
            )

        await _purge_expired_oauth_rows(app=app)

        async with app.state.mcp_session_manager.run():
            yield

        await close_pool(app.state.db_pool)

    return lifespan


def _add_middleware(
    app: FastAPI,
    identity_provider: IdentityProvider | None,
    allowed_origins: tuple[str, ...],
) -> None:
    """Attach the identity and CORS middleware, in that order.

    FastAPI applies middleware in reverse order of addition, so CORS is added
    last to make it outermost. That is what puts CORS headers on the identity
    middleware's own 401s, which a browser needs in order to read them.
    """
    app.add_middleware(IdentityMiddleware, identity_provider=identity_provider)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _include_api_routers(app: FastAPI, identity_provider: IdentityProvider | None) -> None:
    """Register the platform's API routers, then whatever the provider contributes.

    All registered before the MCP sub-app is mounted, because a mount matches every
    path beneath it and would otherwise shadow a router sharing its prefix. A
    provider's consent endpoint lives under ``/mcp``, so this ordering is what makes
    it reachable.
    """
    app.include_router(runs_router)
    app.include_router(pdf_export_router)
    app.include_router(bundle_router)
    app.include_router(multi_export_router)
    app.include_router(analysis_router)
    app.include_router(dashboard_router)
    app.include_router(scenarios_router)
    if identity_provider is None:
        return
    for router in identity_provider.routers():
        app.include_router(router)


def create_app(
    identity_provider: IdentityProvider | None,
    runtime_config: ServerRuntimeConfig,
) -> FastAPI:
    """Build the FastAPI application.

    State the routers read is set here rather than in the lifespan wherever it is
    known at construction time, so a caller that never runs the lifespan still
    gets an app whose unauthenticated endpoints answer.
    """
    app = FastAPI(
        title="GlossoGen Simulation Server",
        lifespan=_build_lifespan(identity_provider=identity_provider),
    )
    app.state.runs_dir = runtime_config.runs_dir
    app.state.analysis_record_cache = AnalysisRecordCache(
        ttl_seconds=RECORD_CACHE_TTL_SECONDS,
        max_runs=RECORD_CACHE_MAX_RUNS,
    )
    app.state.feature_flags = runtime_config.feature_flags
    # Assigned before the lifespan can read them, whether or not MCP is mounted.
    app.state.oauth_storage = None
    app.state.mcp_session_manager = StubSessionManager()

    register_error_logging_handlers(app)
    _add_middleware(
        app=app,
        identity_provider=identity_provider,
        allowed_origins=runtime_config.allowed_origins,
    )
    _include_api_routers(app=app, identity_provider=identity_provider)

    if runtime_config.oauth_issuer_url is None:
        logger.warning(
            "OAUTH_ISSUER_URL not set, so the MCP server is disabled. "
            "Set OAUTH_ISSUER_URL to enable the MCP endpoint at /mcp."
        )
    else:
        mount_oauth_and_mcp(
            app=app,
            runs_dir=runtime_config.runs_dir,
            oauth_issuer_url=runtime_config.oauth_issuer_url,
            identity_provider=identity_provider,
        )

    # Last, so the unauthenticated endpoints keep the position in the OpenAPI
    # path order they had when they were declared on the app directly.
    app.include_router(health_router)
    return app
