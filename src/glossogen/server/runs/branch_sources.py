"""Lists the runs that have been used as derivation parents (the branches view).

The branches page groups derived runs (replace-agent, fork-at-round,
cross-run-replace-agent) under the source run they branch from. There are far
fewer sources than derivations, so this module resolves the distinct sources
first (one aggregate Postgres query, or in no-database local mode a scan of
each run's derivation manifests) and enriches only those source runs into full
summaries. It never builds a summary for the whole run set to find branches.
"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

from fastapi import Request

from glossogen.db.pool import DbPool
from glossogen.db.queries import list_derived_source_counts
from glossogen.run_storage.run_discovery import build_summary, discover_run_descriptors
from glossogen.run_storage.run_identity import compose_run_id
from glossogen.server.runs.derived_run_references import derived_runs_on_disk
from glossogen.server.runs.lookup import get_identity
from glossogen.server.runs.models import BranchSourceSummary

logger = logging.getLogger(__name__)


async def _build_source_summary(
    runs_dir: Path,
    scenario: str,
    run_dir_name: str,
    derived_count: int,
) -> BranchSourceSummary | None:
    """Enrich one source run into a summary; ``None`` if its dir is unreadable.

    A source whose own derivation manifest cannot be read is logged and left
    out rather than failing the whole branches page.
    """
    try:
        summary = await build_summary(
            scenario_name=scenario,
            timestamp_dir=runs_dir / scenario / run_dir_name,
            evaluation_content_hash=None,
        )
    except Exception:
        logger.exception("Skipping branch source %s/%s: summary failed", scenario, run_dir_name)
        return None
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


class _SourceOnDisk(NamedTuple):
    """A parent run found on disk and how many runs derive from it."""

    scenario: str
    run_dir_name: str
    derived_count: int


def _sources_on_disk_sync(runs_dir: Path) -> list[_SourceOnDisk]:
    """Tally each derived run against its timeline parent, newest parent first.

    Blocking. Reads only directory listings and derivation manifests. A parent
    is kept only when its own directory still holds an event log.
    """
    descriptors = discover_run_descriptors(runs_dir=runs_dir)
    counts: dict[str, int] = {}
    for derived in derived_runs_on_disk(runs_dir=runs_dir, descriptors=descriptors):
        counts[derived.parent_run_id] = counts.get(derived.parent_run_id, 0) + 1
    sources: list[_SourceOnDisk] = []
    for descriptor in descriptors:
        run_id = compose_run_id(
            scenario_name=descriptor.scenario_name, run_dir_name=descriptor.run_dir_name
        )
        derived_count = counts.get(run_id)
        if derived_count is None:
            continue
        sources.append(
            _SourceOnDisk(
                scenario=descriptor.scenario_name,
                run_dir_name=descriptor.run_dir_name,
                derived_count=derived_count,
            )
        )
    return sources


async def _list_branch_sources_from_disk(runs_dir: Path) -> list[BranchSourceSummary]:
    """Resolve sources by scanning the filesystem (no-database local mode).

    Finds the parents from the derivation manifests alone, then builds a
    summary for each parent only, as the database path does.
    """
    sources = await asyncio.to_thread(_sources_on_disk_sync, runs_dir=runs_dir)
    tasks = [
        asyncio.create_task(
            _build_source_summary(
                runs_dir=runs_dir,
                scenario=source.scenario,
                run_dir_name=source.run_dir_name,
                derived_count=source.derived_count,
            )
        )
        for source in sources
    ]
    results = await asyncio.gather(*tasks)
    return [source for source in results if source is not None]


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
