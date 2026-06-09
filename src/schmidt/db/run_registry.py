"""Insert ``runs`` rows from contexts that own a fresh DB connection.

The FastAPI request path uses the connection pool on ``app.state.db_pool``;
this module is for code paths that don't have a pool: the CLI subprocess
spawned by ``launch_simulation`` and any one-shot script (e.g. the backfill).
Each call opens, uses, and closes its own ``AsyncConnection``.
"""

import logging
from datetime import datetime

import psycopg

from schmidt.db.pool import get_database_url
from schmidt.db.queries import (
    get_group_by_slug,
    insert_run,
    insert_run_if_absent,
    update_run_status,
)

logger = logging.getLogger(__name__)


def _resolve_async_conninfo() -> str:
    """Return a psycopg3 conninfo string from ``DATABASE_URL``.

    ``psycopg.AsyncConnection.connect`` is happy with the plain
    ``postgresql://`` URL, no SQLAlchemy-style ``+psycopg`` scheme is needed
    here.
    """
    return get_database_url()


async def register_run_standalone(
    group_slug: str,
    scenario: str,
    run_dir_name: str,
    status: str,
    created_at: datetime,
    created_by_user_id: str | None,
    source_run_scenario: str | None,
    source_run_dir_name: str | None,
) -> None:
    """Open a one-shot connection and insert a ``runs`` row.

    Raises if the group slug is unknown — that's a misconfiguration and the
    subprocess should abort rather than silently lose ownership info.
    """
    conninfo = _resolve_async_conninfo()
    async with await psycopg.AsyncConnection.connect(conninfo=conninfo) as conn:
        group = await get_group_by_slug(conn=conn, slug=group_slug)
        if group is None:
            raise RuntimeError(f"Unknown group slug for run registration: {group_slug!r}")
        await insert_run(
            conn=conn,
            group_id=group.id,
            scenario=scenario,
            run_dir_name=run_dir_name,
            status=status,
            created_at=created_at,
            created_by_user_id=created_by_user_id,
            source_run_scenario=source_run_scenario,
            source_run_dir_name=source_run_dir_name,
        )
    logger.info(
        "Registered run in DB: scenario=%s run_dir_name=%s group=%s",
        scenario,
        run_dir_name,
        group_slug,
    )


async def register_run_if_absent_standalone(
    group_slug: str,
    scenario: str,
    run_dir_name: str,
    status: str,
    created_at: datetime,
    created_by_user_id: str | None,
    source_run_scenario: str | None,
    source_run_dir_name: str | None,
) -> bool:
    """Same as ``register_run_standalone`` but idempotent.

    Returns True if a row was inserted, False if one was already present.
    Used by the backfill script to skip already-indexed runs.
    """
    conninfo = _resolve_async_conninfo()
    async with await psycopg.AsyncConnection.connect(conninfo=conninfo) as conn:
        group = await get_group_by_slug(conn=conn, slug=group_slug)
        if group is None:
            raise RuntimeError(f"Unknown group slug for run registration: {group_slug!r}")
        inserted = await insert_run_if_absent(
            conn=conn,
            group_id=group.id,
            scenario=scenario,
            run_dir_name=run_dir_name,
            status=status,
            created_at=created_at,
            created_by_user_id=created_by_user_id,
            source_run_scenario=source_run_scenario,
            source_run_dir_name=source_run_dir_name,
        )
    return inserted


async def update_run_status_standalone(
    *,
    scenario: str,
    run_dir_name: str,
    status: str,
) -> None:
    """Open a one-shot connection and update the ``status`` column for a run.

    Used by the autonomous supervisor to flip the row from ``starting`` to
    the terminal status (e.g. ``scenario_complete``) when the simulation
    finishes. Without this call, every run produced by the local CLI sits
    indefinitely at ``starting``, hiding from the FE's completed-runs view.
    """
    conninfo = _resolve_async_conninfo()
    async with await psycopg.AsyncConnection.connect(conninfo=conninfo) as conn:
        await update_run_status(
            conn=conn,
            scenario=scenario,
            run_dir_name=run_dir_name,
            status=status,
        )
