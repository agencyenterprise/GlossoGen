"""Listing of runs owned by a group.

With Postgres, the ``runs`` table holds the authoritative set of runs per group
and ``build_summary`` enriches each row from the per-run on-disk summary cache.
In no-database local mode (``pool`` is ``None``) the listing falls back to
``discover_runs``, scanning the filesystem directly — the single ``local`` group
owns every run, so no ownership filter is needed.
"""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from fastapi import Request

from schmidt.db.pool import DbPool
from schmidt.db.queries import list_runs_for_group as db_list_runs_for_group
from schmidt.server.runs.discovery import build_summary, discover_runs
from schmidt.server.runs.lookup import get_identity
from schmidt.server.runs.models import RunSummary

logger = logging.getLogger(__name__)

# Cap for one listing call; the Postgres index keeps the ordered scan cheap.
_LIST_LIMIT = 10_000


async def list_runs_owned_by_group(
    pool: DbPool | None,
    runs_dir: Path,
    group_id: UUID,
    scenario_filter: str | None,
) -> list[RunSummary]:
    """Core listing primitive: DB query + per-row on-disk enrichment.

    Used by both the REST route wrapper (``list_runs_for_group``) and the MCP
    tool layer, which has no FastAPI ``Request`` to pull state from. When
    ``pool`` is ``None`` (no-database local mode) the runs are discovered from
    the filesystem instead.
    """
    if pool is None:
        summaries = await discover_runs(runs_dir=runs_dir)
        if scenario_filter is None:
            return summaries
        return [s for s in summaries if s.scenario_name == scenario_filter]

    async with pool.connection() as conn:
        rows = await db_list_runs_for_group(
            conn=conn,
            group_id=group_id,
            scenario=scenario_filter,
            limit=_LIST_LIMIT,
            offset=0,
        )

    tasks = [
        asyncio.create_task(
            build_summary(
                scenario_name=row.scenario,
                timestamp_dir=runs_dir / row.scenario / row.run_dir_name,
            )
        )
        for row in rows
    ]
    results = await asyncio.gather(*tasks)
    return [s for s in results if s is not None]


async def list_runs_for_group(
    request: Request,
    scenario_filter: str | None,
) -> list[RunSummary]:
    """REST-layer wrapper around :func:`list_runs_owned_by_group`.

    Pulls ``runs_dir``, ``pool``, and the active ``group_id`` from
    ``request`` state, then delegates.
    """
    identity = get_identity(request=request)
    return await list_runs_owned_by_group(
        pool=request.app.state.db_pool,
        runs_dir=request.app.state.runs_dir,
        group_id=identity.active_group_id,
        scenario_filter=scenario_filter,
    )
