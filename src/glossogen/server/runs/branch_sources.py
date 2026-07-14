"""Lists the runs that have been used as derivation parents (the branches view).

The branches page groups derived runs (replace-agent, resume-at-round,
cross-run-replace-agent) under the source run they branch from. There are far
fewer sources than derivations, so this module resolves the distinct sources
first (one aggregate Postgres query, or a filesystem scan in no-database local
mode) and enriches only those source runs into full summaries. It never
enumerates the whole run set to find branches.
"""

import asyncio
import logging
from pathlib import Path
from uuid import UUID

from fastapi import Request

from glossogen.db.pool import DbPool
from glossogen.db.queries import list_derived_source_counts
from glossogen.server.runs.derived_run_references import timeline_parent_run_id
from glossogen.server.runs.discovery import build_summary, discover_runs
from glossogen.server.runs.lookup import get_identity
from glossogen.server.runs.models import BranchSourceSummary, RunSummary

logger = logging.getLogger(__name__)


async def _build_source_summary(
    runs_dir: Path,
    scenario: str,
    run_dir_name: str,
    derived_count: int,
) -> BranchSourceSummary | None:
    """Enrich one source run into a summary; ``None`` if its dir is unreadable."""
    summary = await build_summary(
        scenario_name=scenario,
        timestamp_dir=runs_dir / scenario / run_dir_name,
        evaluation_content_hash=None,
    )
    if summary is None:
        logger.warning(
            "Skipping branch source %s/%s: build_summary returned None",
            scenario,
            run_dir_name,
        )
        return None
    return BranchSourceSummary(source_run=summary, derived_count=derived_count)


async def _list_branch_sources_from_db(
    pool: DbPool,
    runs_dir: Path,
    group_id: UUID,
) -> list[BranchSourceSummary]:
    """Resolve sources from the aggregate Postgres query, enriching each parent."""
    async with pool.connection() as conn:
        rows = await list_derived_source_counts(conn=conn, group_id=group_id)
    tasks = [
        asyncio.create_task(
            _build_source_summary(
                runs_dir=runs_dir,
                scenario=row.scenario,
                run_dir_name=row.run_dir_name,
                derived_count=row.derived_count,
            )
        )
        for row in rows
    ]
    results = await asyncio.gather(*tasks)
    return [source for source in results if source is not None]


async def _list_branch_sources_from_disk(runs_dir: Path) -> list[BranchSourceSummary]:
    """Resolve sources by scanning the filesystem (no-database local mode).

    Builds every summary once, tallies each derived run against its timeline
    parent, then emits one entry per parent that resolves to a known summary.
    """
    summaries = await discover_runs(runs_dir=runs_dir)
    by_run_id: dict[str, RunSummary] = {summary.run_id: summary for summary in summaries}
    counts: dict[str, int] = {}
    for summary in summaries:
        parent_run_id = timeline_parent_run_id(summary=summary)
        if parent_run_id is None:
            continue
        counts[parent_run_id] = counts.get(parent_run_id, 0) + 1

    sources: list[BranchSourceSummary] = []
    for parent_run_id, derived_count in counts.items():
        source_summary = by_run_id.get(parent_run_id)
        if source_summary is None:
            continue
        sources.append(
            BranchSourceSummary(source_run=source_summary, derived_count=derived_count)
        )
    sources.sort(key=lambda entry: entry.source_run.timestamp, reverse=True)
    return sources


async def list_branch_sources(
    pool: DbPool | None,
    runs_dir: Path,
    group_id: UUID,
) -> list[BranchSourceSummary]:
    """Return every source run with derived children, newest parent first."""
    if pool is None:
        return await _list_branch_sources_from_disk(runs_dir=runs_dir)
    return await _list_branch_sources_from_db(
        pool=pool,
        runs_dir=runs_dir,
        group_id=group_id,
    )


async def list_branch_sources_for_group(request: Request) -> list[BranchSourceSummary]:
    """REST-layer wrapper around :func:`list_branch_sources`."""
    identity = get_identity(request=request)
    return await list_branch_sources(
        pool=request.app.state.db_pool,
        runs_dir=request.app.state.runs_dir,
        group_id=identity.active_group_id,
    )
