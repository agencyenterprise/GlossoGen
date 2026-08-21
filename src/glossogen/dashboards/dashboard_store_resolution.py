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
    pool = request.app.state.db_pool
    if pool is None:
        runs_dir: Path = request.app.state.runs_dir
        return FilesystemDashboardStore(runs_dir=runs_dir)
    return PostgresDashboardStore(pool=pool)
