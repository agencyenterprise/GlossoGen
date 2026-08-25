"""Keeping the runs table's ``labels`` column in step with each run's ``labels.json``.

The file is the source of truth; the column is what the label union and label
filtering read. Orchestrator scripts write the file directly without touching the
server, so the mirror is repaired wherever the server has just read the file
anyway: the page window of a listing, one run's detail, and a startup backfill
for rows that have never been mirrored (``labels IS NULL``).

Healing is awaited, not fired and forgotten: the pool closes when the app's
lifespan exits, and an orphaned task racing shutdown would land on a closed
pool. In the common no-drift case the plan is empty and no connection is taken.
"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

from fastapi import Request

from glossogen.db.pool import DbPool
from glossogen.db.queries import list_runs_missing_labels, update_run_labels
from glossogen.db.rows import RunRow
from glossogen.server.runs.discovery import ResolvedRun, RunDescriptor, read_run_labels
from glossogen.server.runs.lookup import get_identity
from glossogen.server.runs.models import RunSummary

logger = logging.getLogger(__name__)

_BACKFILL_CHUNK_SIZE = 500


class LabelMirrorUpdate(NamedTuple):
    """One run whose labels column must be rewritten to match its file."""

    scenario_name: str
    run_dir_name: str
    labels: list[str]


def plan_label_mirror_updates(
    descriptors: list[RunDescriptor],
    summaries: list[RunSummary],
) -> list[LabelMirrorUpdate]:
    """Compare summaries' disk labels against their rows' mirrored labels.

    A summary's labels come from ``labels.json``; the descriptor's from the runs
    row. ``None`` on the descriptor means the row was never mirrored, which is
    as much drift as a stale list. A summary with no matching descriptor (a run
    deleted between enumeration and enrichment, or a filesystem-mode descriptor
    list) plans nothing.
    """
    mirrored = {
        (descriptor.scenario_name, descriptor.run_dir_name): descriptor.labels
        for descriptor in descriptors
    }
    updates: list[LabelMirrorUpdate] = []
    for summary in summaries:
        run_dir_name = summary.run_id.split("/", 1)[1]
        key = (summary.scenario_name, run_dir_name)
        if key not in mirrored:
            continue
        if mirrored[key] == summary.labels:
            continue
        updates.append(
            LabelMirrorUpdate(
                scenario_name=summary.scenario_name,
                run_dir_name=run_dir_name,
                labels=list(summary.labels),
            )
        )
    return updates


async def heal_label_mirror(
    pool: DbPool | None,
    group_id: UUID,
    descriptors: list[RunDescriptor],
    summaries: list[RunSummary],
) -> None:
    """Repair the mirror for the runs whose files were just read. Never raises.

    Call this on a page window, never on a whole-group listing: the point is to
    piggyback on file reads a request already paid for, not to add thousands of
    UPDATEs to one GET.
    """
    if pool is None:
        return
    updates = plan_label_mirror_updates(descriptors=descriptors, summaries=summaries)
    if not updates:
        return
    try:
        async with pool.connection() as conn:
            for update in updates:
                await update_run_labels(
                    conn=conn,
                    group_id=group_id,
                    scenario=update.scenario_name,
                    run_dir_name=update.run_dir_name,
                    labels=update.labels,
                )
    except Exception:
        logger.exception("Failed to heal the run-labels mirror (%d updates)", len(updates))
        return
    logger.info("Healed the run-labels mirror for %d runs", len(updates))


async def heal_run_labels_after_read(
    request: Request,
    resolved: ResolvedRun,
    run_dir_name: str,
    disk_labels: list[str],
) -> None:
    """Repair one run's mirror after its ``labels.json`` was read for a response.

    ``resolved.db_labels`` was fetched by the lookup the request already paid
    for; ``None`` there means the row was never mirrored, which is repaired
    like any other drift. Never raises.
    """
    pool = request.app.state.db_pool
    if pool is None:
        return
    if resolved.db_labels == disk_labels:
        return
    identity = get_identity(request=request)
    try:
        async with pool.connection() as conn:
            await update_run_labels(
                conn=conn,
                group_id=identity.active_group_id,
                scenario=resolved.scenario_name,
                run_dir_name=run_dir_name,
                labels=disk_labels,
            )
    except Exception:
        logger.exception(
            "Failed to heal the labels mirror for run %s/%s",
            resolved.scenario_name,
            run_dir_name,
        )


def _read_labels_for_rows(runs_dir: Path, rows: list[RunRow]) -> list[LabelMirrorUpdate]:
    """Read each row's ``labels.json`` (blocking); a missing or broken file reads as none."""
    return [
        LabelMirrorUpdate(
            scenario_name=row.scenario,
            run_dir_name=row.run_dir_name,
            labels=read_run_labels(run_dir=runs_dir / row.scenario / row.run_dir_name),
        )
        for row in rows
    ]


async def backfill_run_label_mirror(pool: DbPool | None, runs_dir: Path) -> None:
    """Mirror labels for every row that has never been mirrored.

    Runs once per boot, before the server accepts requests. Only the first boot
    after the column lands pays a full scan; a scanned row is written as its
    file's labels (a missing file as ``[]``), never left ``NULL``, so later
    boots find nothing to do. A chunk that fails is logged and skipped; its
    rows stay ``NULL`` and are retried next boot.
    """
    if pool is None:
        return
    async with pool.connection() as conn:
        rows = await list_runs_missing_labels(conn=conn)
    if not rows:
        return
    mirrored = 0
    for start in range(0, len(rows), _BACKFILL_CHUNK_SIZE):
        chunk = rows[start : start + _BACKFILL_CHUNK_SIZE]
        try:
            updates = await asyncio.to_thread(_read_labels_for_rows, runs_dir, chunk)
            async with pool.connection() as conn:
                for row, update in zip(chunk, updates, strict=True):
                    await update_run_labels(
                        conn=conn,
                        group_id=row.group_id,
                        scenario=update.scenario_name,
                        run_dir_name=update.run_dir_name,
                        labels=update.labels,
                    )
        except Exception:
            logger.exception(
                "Run-labels backfill chunk failed (%d rows starting at %d); will retry next boot",
                len(chunk),
                start,
            )
            continue
        mirrored += len(updates)
    logger.info("Backfilled the run-labels mirror for %d of %d runs", mirrored, len(rows))
