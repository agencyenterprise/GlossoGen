"""FastAPI router for saved dashboards.

A dashboard belongs to a group, and every request is scoped by the identity the
middleware attached, so a dashboard id from another group reads as absent rather than
as forbidden. That is the same shape run lookup uses: not-yours and not-there are one
answer, and neither confirms the other group's id exists.

Naming collides on purpose. A group's dashboards are referred to by name, so a second
"Noise sweep" is refused with a 409 rather than silently made.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from glossogen.dashboards.dashboard_models import (
    Dashboard,
    DashboardContent,
    DashboardSummary,
)
from glossogen.dashboards.dashboard_store import DashboardNameTaken
from glossogen.dashboards.dashboard_store_resolution import dashboard_store_for
from glossogen.server.runs.lookup import get_identity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")


def _name_taken(name: str) -> HTTPException:
    """The refusal a duplicate name gets."""
    return HTTPException(
        status_code=409,
        detail=f"This group already has a dashboard called {name!r}.",
    )


@router.get("/dashboards", response_model=list[DashboardSummary])
async def list_dashboards(request: Request) -> list[DashboardSummary]:
    """List the group's dashboards, most recently updated first."""
    identity = get_identity(request=request)
    store = dashboard_store_for(request=request)
    return await store.list_dashboards(group_id=identity.active_group_id)


@router.post("/dashboards", response_model=Dashboard, status_code=201)
async def create_dashboard(body: DashboardContent, request: Request) -> Dashboard:
    """Save a new dashboard for the group."""
    identity = get_identity(request=request)
    store = dashboard_store_for(request=request)
    try:
        dashboard = await store.create_dashboard(
            group_id=identity.active_group_id,
            content=body,
            created_by=identity.user_id,
        )
    except DashboardNameTaken as exc:
        raise _name_taken(name=body.name) from exc
    logger.info("Created dashboard %s (%s)", dashboard.dashboard_id, dashboard.name)
    return dashboard


@router.get("/dashboards/{dashboard_id}", response_model=Dashboard)
async def get_dashboard(dashboard_id: UUID, request: Request) -> Dashboard:
    """Read one of the group's dashboards."""
    identity = get_identity(request=request)
    store = dashboard_store_for(request=request)
    dashboard = await store.get_dashboard(
        group_id=identity.active_group_id, dashboard_id=dashboard_id
    )
    if dashboard is None:
        raise HTTPException(status_code=404, detail="No such dashboard.")
    return dashboard


@router.put("/dashboards/{dashboard_id}", response_model=Dashboard)
async def update_dashboard(
    dashboard_id: UUID,
    body: DashboardContent,
    request: Request,
) -> Dashboard:
    """Replace a dashboard's name, description, selection, filters, and charts."""
    identity = get_identity(request=request)
    store = dashboard_store_for(request=request)
    try:
        dashboard = await store.update_dashboard(
            group_id=identity.active_group_id,
            dashboard_id=dashboard_id,
            content=body,
        )
    except DashboardNameTaken as exc:
        raise _name_taken(name=body.name) from exc
    if dashboard is None:
        raise HTTPException(status_code=404, detail="No such dashboard.")
    return dashboard


@router.delete("/dashboards/{dashboard_id}", status_code=204)
async def delete_dashboard(dashboard_id: UUID, request: Request) -> Response:
    """Delete one of the group's dashboards."""
    identity = get_identity(request=request)
    store = dashboard_store_for(request=request)
    deleted = await store.delete_dashboard(
        group_id=identity.active_group_id, dashboard_id=dashboard_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="No such dashboard.")
    return Response(status_code=204)
