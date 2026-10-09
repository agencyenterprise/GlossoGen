"""Choosing where this server's dashboards live.

The same test the run lookup uses: a pool means Postgres, no pool means the
filesystem. Nothing above this line knows which one answered.
"""

from pathlib import Path

from fastapi import Request

from glossogen.dashboards.dashboard_store import DashboardStore
from glossogen.dashboards.filesystem_dashboard_store import FilesystemDashboardStore
from glossogen.dashboards.postgres_dashboard_store import PostgresDashboardStore


def dashboard_store_for(request: Request) -> DashboardStore:
    """Return the store backing this server's dashboards."""
    existing: DashboardStore | None = getattr(request.app.state, "dashboard_store", None)
    if existing is not None:
        return existing
    pool = request.app.state.db_pool
    if pool is None:
        runs_dir: Path = request.app.state.runs_dir
        store: DashboardStore = FilesystemDashboardStore(runs_dir=runs_dir)
    else:
        store = PostgresDashboardStore(pool=pool)
    request.app.state.dashboard_store = store
    return store
