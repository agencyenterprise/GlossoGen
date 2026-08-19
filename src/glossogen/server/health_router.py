"""Unauthenticated endpoints: the health probe and the public server config.

Both bypass the identity middleware, so they answer before any group is
resolved. ``/api/health`` is what the deployment platform probes; the frontend
reads ``/api/server-config`` to learn which optional capabilities are enabled.
"""

from fastapi import APIRouter
from starlette.requests import Request

from glossogen.server.feature_flags import FeatureFlags
from glossogen.server.response_models import HealthResponse, HealthStatus, ServerConfigResponse

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status=HealthStatus.OK)


@router.get("/api/server-config", response_model=ServerConfigResponse)
async def server_config(request: Request) -> ServerConfigResponse:
    """Public server feature flags consumed by the frontend."""
    feature_flags: FeatureFlags = request.app.state.feature_flags
    return ServerConfigResponse(evaluations_enabled=feature_flags.evaluations_enabled)
