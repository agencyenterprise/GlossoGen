"""Listing of runs owned by a group.

Listing is split into a cheap descriptor phase and an expensive enrichment
phase. :func:`enumerate_run_descriptors` produces an ordered, lightweight
``RunDescriptor`` list (one indexed query with Postgres, a directory walk in
no-database local mode). Cheap filters — scenario, then labels read from each
run's ``labels.json`` — are applied to descriptors, and only the requested page
is enriched into full :class:`RunSummary` objects via ``build_summary``.

Labels live on disk (``labels.json``), never in the database, so label
filtering reads the filesystem identically with and without a database.
"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

from fastapi import Request

from glossogen.db.pool import DbPool
from glossogen.db.queries import list_runs_for_group as db_list_runs_for_group
from glossogen.models.event import RunStatus
from glossogen.server.runs.discovery import (
    RunDescriptor,
    build_summary,
    compose_run_id,
    discover_run_descriptors,
    read_run_labels,
)
from glossogen.server.runs.lookup import get_identity
from glossogen.server.runs.models import RunSummary

logger = logging.getLogger(__name__)

# Cap for one listing call; the Postgres index keeps the ordered scan cheap.
_LIST_LIMIT = 10_000


class PaginatedRuns(NamedTuple):
    """One page of run summaries plus the total matching the active filters."""

    runs: list[RunSummary]
    total: int


async def enumerate_run_descriptors(
    pool: DbPool | None,
    runs_dir: Path,
    group_id: UUID,
    scenario_filter: str | None,
) -> list[RunDescriptor]:
    """Return ordered (newest-first) run descriptors for a group, no enrichment.

    With Postgres, the ``runs`` table is authoritative and the descriptor list
    comes from one indexed query. In no-database local mode (``pool`` is
    ``None``) the single ``local`` group owns every run, so the descriptors are
    discovered from the filesystem.
    """
    if pool is None:
        descriptors = discover_run_descriptors(runs_dir=runs_dir)
        if scenario_filter is None:
            return descriptors
        return [d for d in descriptors if d.scenario_name == scenario_filter]

    async with pool.connection() as conn:
        rows = await db_list_runs_for_group(
            conn=conn,
            group_id=group_id,
            scenario=scenario_filter,
            limit=_LIST_LIMIT,
            offset=0,
        )
    return [
        RunDescriptor(
            scenario_name=row.scenario,
            run_dir_name=row.run_dir_name,
            timestamp=row.created_at,
            evaluation_content_hash=row.evaluation_content_hash,
        )
        for row in rows
    ]


async def _build_summaries(
    runs_dir: Path,
    descriptors: list[RunDescriptor],
) -> list[RunSummary]:
    """Enrich descriptors into summaries concurrently, dropping invalid runs."""
    tasks = [
        asyncio.create_task(
            build_summary(
                scenario_name=descriptor.scenario_name,
                timestamp_dir=runs_dir / descriptor.scenario_name / descriptor.run_dir_name,
                evaluation_content_hash=descriptor.evaluation_content_hash,
            )
        )
        for descriptor in descriptors
    ]
    results = await asyncio.gather(*tasks)
    return [summary for summary in results if summary is not None]


def _matches_labels(run_dir: Path, required: frozenset[str]) -> bool:
    """True when the run carries every required label (AND semantics)."""
    return required.issubset(read_run_labels(run_dir=run_dir))


async def list_runs_page(
    pool: DbPool | None,
    runs_dir: Path,
    group_id: UUID,
    scenarios: list[str],
    labels: list[str],
    run_id_contains: str | None,
    status: RunStatus | None,
    contains_agent_id: str | None,
    offset: int,
    limit: int,
) -> PaginatedRuns:
    """Return one page of run summaries plus the total matching the filters.

    Scenario, run-id, and label filters are applied to descriptors before
    enrichment, so the common path (no ``status`` / ``contains_agent_id``
    filter) enriches only the page. ``scenarios`` keeps runs whose scenario is
    in the set (OR semantics; empty means all). ``run_id_contains`` keeps runs
    whose ``scenario/run_dir_name`` id contains the substring (case-insensitive).
    ``status`` and ``contains_agent_id`` depend on enriched fields, so when
    either is set every descriptor-matching candidate is enriched and filtered
    before the page is sliced.
    """
    descriptors = await enumerate_run_descriptors(
        pool=pool,
        runs_dir=runs_dir,
        group_id=group_id,
        scenario_filter=None,
    )
    if scenarios:
        wanted = frozenset(scenarios)
        descriptors = [d for d in descriptors if d.scenario_name in wanted]
    if run_id_contains:
        needle = run_id_contains.lower()
        descriptors = [
            d
            for d in descriptors
            if needle
            in compose_run_id(scenario_name=d.scenario_name, run_dir_name=d.run_dir_name).lower()
        ]
    if labels:
        required = frozenset(labels)
        descriptors = [
            descriptor
            for descriptor in descriptors
            if _matches_labels(
                run_dir=runs_dir / descriptor.scenario_name / descriptor.run_dir_name,
                required=required,
            )
        ]

    if status is None and contains_agent_id is None:
        page = await _build_summaries(
            runs_dir=runs_dir,
            descriptors=descriptors[offset : offset + limit],
        )
        return PaginatedRuns(runs=page, total=len(descriptors))

    summaries = await _build_summaries(runs_dir=runs_dir, descriptors=descriptors)
    if contains_agent_id is not None:
        summaries = [
            summary
            for summary in summaries
            if any(am.agent_id == contains_agent_id for am in summary.agent_models)
        ]
    if status is not None:
        summaries = [summary for summary in summaries if summary.status == status]
    return PaginatedRuns(runs=summaries[offset : offset + limit], total=len(summaries))


async def list_runs_owned_by_group(
    pool: DbPool | None,
    runs_dir: Path,
    group_id: UUID,
    scenario_filter: str | None,
) -> list[RunSummary]:
    """Return every summary owned by a group, newest-first (no pagination).

    Used by the MCP tool layer and the bundle exporter, which have no FastAPI
    ``Request`` and need the full result set to apply their own filters.
    """
    descriptors = await enumerate_run_descriptors(
        pool=pool,
        runs_dir=runs_dir,
        group_id=group_id,
        scenario_filter=scenario_filter,
    )
    return await _build_summaries(runs_dir=runs_dir, descriptors=descriptors)


async def list_runs_for_group(
    request: Request,
    scenario_filter: str | None,
) -> list[RunSummary]:
    """REST-layer wrapper returning every summary owned by the active group."""
    identity = get_identity(request=request)
    return await list_runs_owned_by_group(
        pool=request.app.state.db_pool,
        runs_dir=request.app.state.runs_dir,
        group_id=identity.active_group_id,
        scenario_filter=scenario_filter,
    )


async def list_runs_page_for_group(
    request: Request,
    scenarios: list[str],
    labels: list[str],
    run_id_contains: str | None,
    status: RunStatus | None,
    contains_agent_id: str | None,
    offset: int,
    limit: int,
) -> PaginatedRuns:
    """REST-layer wrapper around :func:`list_runs_page`."""
    identity = get_identity(request=request)
    return await list_runs_page(
        pool=request.app.state.db_pool,
        runs_dir=request.app.state.runs_dir,
        group_id=identity.active_group_id,
        scenarios=scenarios,
        labels=labels,
        run_id_contains=run_id_contains,
        status=status,
        contains_agent_id=contains_agent_id,
        offset=offset,
        limit=limit,
    )


async def list_all_labels_for_group(request: Request) -> list[str]:
    """Return the sorted union of labels across the active group's runs.

    Reads only ``labels.json`` per run — never builds summaries — so the label
    filter UI stays cheap regardless of run count.
    """
    identity = get_identity(request=request)
    pool = request.app.state.db_pool
    runs_dir: Path = request.app.state.runs_dir
    descriptors = await enumerate_run_descriptors(
        pool=pool,
        runs_dir=runs_dir,
        group_id=identity.active_group_id,
        scenario_filter=None,
    )
    seen: set[str] = set()
    for descriptor in descriptors:
        run_dir = runs_dir / descriptor.scenario_name / descriptor.run_dir_name
        seen.update(read_run_labels(run_dir=run_dir))
    return sorted(seen)
