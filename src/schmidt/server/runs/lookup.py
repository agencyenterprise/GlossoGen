"""Group-scoped run lookup helpers used by every cross-run router.

Every request that addresses a specific run (detail, fork, replace-agent,
prod-upload, resume, bundle, etc.) routes through ``resolve_run_or_404``,
which gates ownership against the Postgres ``runs`` table before returning
the on-disk path. This is the single chokepoint that enforces same-group
isolation: a run owned by group A is invisible (HTTP 404) to a request
arriving with group B's identity.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, Request

from schmidt.db.queries import get_run, insert_run
from schmidt.server.identity.identity_model import Identity
from schmidt.server.runs.discovery import ResolvedRun

logger = logging.getLogger(__name__)


def get_identity(request: Request) -> Identity:
    """Pull the per-request ``Identity`` stamped by ``ClerkIdentityMiddleware``."""
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(
            status_code=500,
            detail="Identity not attached to request — middleware misconfigured",
        )
    return identity


async def resolve_run_or_404(
    request: Request,
    scenario: str,
    run_dir_name: str,
) -> ResolvedRun:
    """Resolve a run owned by the active group; raise 404 otherwise.

    Order of checks:

    1. Postgres ``runs`` row exists for ``(active_group_id, scenario, run_dir_name)``.
    2. The on-disk run directory and its JSONL exist.

    A run row without files on disk indicates a partially deleted run or a
    cross-host filesystem inconsistency; both cases surface as 404.
    """
    runs_dir: Path = request.app.state.runs_dir
    pool = request.app.state.db_pool
    identity = get_identity(request=request)

    async with pool.connection() as conn:
        row = await get_run(
            conn=conn,
            group_id=identity.active_group_id,
            scenario=scenario,
            run_dir_name=run_dir_name,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")

    run_dir = runs_dir / scenario / run_dir_name
    jsonl_path = run_dir / f"{scenario}.jsonl"
    if not run_dir.is_dir() or not jsonl_path.exists():
        logger.warning(
            "Run row %s/%s present in DB but missing on disk at %s",
            scenario,
            run_dir_name,
            run_dir,
        )
        raise HTTPException(status_code=404, detail="Run files missing on disk")
    return ResolvedRun(run_dir=run_dir, scenario_name=scenario)


async def register_new_run(
    request: Request,
    scenario: str,
    run_dir_name: str,
    status: str,
    source_run_scenario: str | None,
    source_run_dir_name: str | None,
) -> None:
    """Insert a ``runs`` row for a freshly claimed run directory.

    Called by every parent-process flow that allocates a new run dir
    (``fork``, ``replace-agent``, ``cross-run-replace-agent``,
    ``resume-at-round``, bundle import). The CLI subprocess has a separate
    path through ``register_run_standalone`` because it doesn't have access
    to the FastAPI connection pool.

    Always strict: callers must only invoke this when the run dir is
    actually new on this host. Idempotent endpoints (bundle import) check
    for an existing row beforehand and skip the call when re-importing.
    """
    pool = request.app.state.db_pool
    identity = get_identity(request=request)
    created_by = None if identity.is_local_mode else identity.user_id
    async with pool.connection() as conn:
        await insert_run(
            conn=conn,
            group_id=identity.active_group_id,
            scenario=scenario,
            run_dir_name=run_dir_name,
            status=status,
            created_at=datetime.now(tz=UTC),
            created_by_user_id=created_by,
            source_run_scenario=source_run_scenario,
            source_run_dir_name=source_run_dir_name,
        )
