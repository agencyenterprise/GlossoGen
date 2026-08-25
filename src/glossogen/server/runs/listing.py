"""Listing of runs owned by a group.

Listing is split into a cheap descriptor phase and an expensive enrichment
phase. :func:`enumerate_run_descriptors` produces an ordered, lightweight
``RunDescriptor`` list (one indexed query with Postgres, a directory walk in
no-database local mode). Cheap filters — scenario, then labels — are applied to
descriptors, and only the requested page is enriched into full
:class:`RunSummary` objects via ``build_summary``.

Labels are authoritative on disk (``labels.json``) and mirrored into the
``runs`` row. With Postgres the label filter and the label union read the
mirror; without one, or for a row not yet mirrored, they read the file.
"""

import asyncio
import base64
import binascii
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

from fastapi import Request

from glossogen.db.pool import DbPool
from glossogen.db.queries import list_distinct_labels_for_group
from glossogen.db.queries import list_runs_for_group as db_list_runs_for_group
from glossogen.knob_filter import KnobFilter, matches_knob_filters
from glossogen.models.event import RunStatus
from glossogen.server.runs.discovery import (
    RunDescriptor,
    build_summary,
    compose_run_id,
    discover_run_descriptors,
    read_run_labels,
    read_scenario_config,
)
from glossogen.server.runs.label_mirror import heal_label_mirror
from glossogen.server.runs.lookup import get_identity
from glossogen.server.runs.models import RunSummary

logger = logging.getLogger(__name__)

# Cap for one listing call; the Postgres index keeps the ordered scan cheap.
_LIST_LIMIT = 10_000

# Field separator inside the encoded keyset cursor (a control char that cannot
# appear in an ISO timestamp, run dir name, or scenario name).
_CURSOR_SEP = "\x1f"


class _KeysetKey(NamedTuple):
    """Total-order key for keyset pagination over the newest-first run list.

    Ordering is ``(timestamp, run_dir_name, scenario_name)`` descending. The
    ``scenario_name`` tiebreak makes the order total even when two scenarios
    have a run directory named for the same unix second.
    """

    timestamp: datetime
    run_dir_name: str
    scenario_name: str


def _descriptor_key(descriptor: RunDescriptor) -> _KeysetKey:
    """Build the keyset key for a run descriptor."""
    return _KeysetKey(
        timestamp=descriptor.timestamp,
        run_dir_name=descriptor.run_dir_name,
        scenario_name=descriptor.scenario_name,
    )


def _summary_key(summary: RunSummary) -> _KeysetKey:
    """Build the keyset key for an enriched run summary."""
    run_dir_name = summary.run_id.split("/", 1)[1]
    return _KeysetKey(
        timestamp=summary.timestamp,
        run_dir_name=run_dir_name,
        scenario_name=summary.scenario_name,
    )


def _encode_cursor(key: _KeysetKey) -> str:
    """Encode a keyset key into an opaque URL-safe cursor string."""
    raw = _CURSOR_SEP.join([key.timestamp.isoformat(), key.run_dir_name, key.scenario_name])
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> _KeysetKey | None:
    """Decode an opaque cursor back into a keyset key, or None if malformed."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        timestamp_iso, run_dir_name, scenario_name = raw.split(_CURSOR_SEP)
        return _KeysetKey(
            timestamp=datetime.fromisoformat(timestamp_iso),
            run_dir_name=run_dir_name,
            scenario_name=scenario_name,
        )
    except (binascii.Error, UnicodeDecodeError, ValueError):
        logger.warning("Ignoring malformed runs-list cursor: %r", cursor)
        return None


class PaginatedRuns(NamedTuple):
    """One page of run summaries.

    Carries the total matching the filters and the keyset cursor for the next
    page, which is ``None`` on the last page."""

    runs: list[RunSummary]
    total: int
    next_cursor: str | None


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
            labels=row.labels,
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


def _filter_descriptors_by_knobs(
    descriptors: list[RunDescriptor],
    runs_dir: Path,
    knob_filters: list[KnobFilter],
) -> list[RunDescriptor]:
    """Keep descriptors whose run's recorded config satisfies every condition.

    Reads one config per candidate, the same shape as the label filter and for
    the same reason: doing this by enriching every candidate into a full summary
    would cost four more filesystem calls each, over the whole cohort rather
    than over the page, and would repeat on every page.
    """
    kept: list[RunDescriptor] = []
    for descriptor in descriptors:
        config = read_scenario_config(
            scenario_name=descriptor.scenario_name,
            timestamp_dir=runs_dir / descriptor.scenario_name / descriptor.run_dir_name,
        )
        if config is None:
            continue
        if matches_knob_filters(scenario_config=config, knob_filters=knob_filters):
            kept.append(descriptor)
    return kept


def descriptor_labels(descriptor: RunDescriptor, runs_dir: Path) -> list[str]:
    """A descriptor's labels: the row's mirror when it has one, else the file.

    ``is not None`` and never truthiness: ``[]`` is a mirrored answer (the run
    has no labels), ``None`` means the row was never mirrored (or the listing
    came from the filesystem) and only the file can say.
    """
    if descriptor.labels is not None:
        return descriptor.labels
    return read_run_labels(run_dir=runs_dir / descriptor.scenario_name / descriptor.run_dir_name)


def _filter_descriptors_by_labels(
    descriptors: list[RunDescriptor],
    runs_dir: Path,
    required: frozenset[str],
) -> list[RunDescriptor]:
    """Keep descriptors whose run carries every required label (AND semantics).

    Descriptors from the runs table answer from their mirrored labels without
    touching disk; the rest read one ``labels.json`` each. Run in a worker
    thread so any per-run reads never block the event loop.
    """
    return [
        descriptor
        for descriptor in descriptors
        if required.issubset(descriptor_labels(descriptor=descriptor, runs_dir=runs_dir))
    ]


async def _apply_descriptor_filters(
    descriptors: list[RunDescriptor],
    runs_dir: Path,
    scenarios: list[str],
    labels: list[str],
    run_id_contains: str | None,
    knob_filters: list[KnobFilter],
) -> list[RunDescriptor]:
    """Narrow descriptors by the filters that need no enrichment.

    ``scenarios`` is OR-matched and empty means all. ``run_id_contains`` matches
    the composed ``scenario/run_dir_name`` id case-insensitively. ``labels`` is
    AND-matched and reads one file per candidate, so it runs in a worker thread.
    ``knob_filters`` are AND-matched against each run's recorded config, read the
    same way and in the same thread.

    Shared by the paginated listing and the export listing so the two cannot
    disagree about what a filter means.
    """
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
        descriptors = await asyncio.to_thread(
            _filter_descriptors_by_labels,
            descriptors,
            runs_dir,
            frozenset(labels),
        )
    if knob_filters:
        descriptors = await asyncio.to_thread(
            _filter_descriptors_by_knobs,
            descriptors,
            runs_dir,
            knob_filters,
        )
    return descriptors


def _indexable_scenario(scenarios: list[str]) -> str | None:
    """The one scenario the indexed query can narrow by, or None.

    One scenario is the common case, and pushing it into the query matters on a
    group holding thousands of runs: without it the whole group comes back and
    the narrowing happens in Python. Several scenarios have no single value to
    push down, so they are filtered here as before.
    """
    if len(scenarios) == 1:
        return scenarios[0]
    return None


def _apply_enriched_filters(
    summaries: list[RunSummary],
    status: RunStatus | None,
    contains_agent_id: str | None,
) -> list[RunSummary]:
    """Apply the filters that need a built summary rather than a descriptor.

    Knob conditions are not among them: they read the recorded config, which
    :func:`_apply_descriptor_filters` reads without building a summary.
    """
    if contains_agent_id is not None:
        summaries = [
            summary
            for summary in summaries
            if any(agent.agent_id == contains_agent_id for agent in summary.agent_models)
        ]
    if status is not None:
        summaries = [summary for summary in summaries if summary.status == status]
    return summaries


async def list_runs_page(
    pool: DbPool | None,
    runs_dir: Path,
    group_id: UUID,
    scenarios: list[str],
    labels: list[str],
    run_id_contains: str | None,
    status: RunStatus | None,
    contains_agent_id: str | None,
    knob_filters: list[KnobFilter],
    cursor: str | None,
    limit: int,
) -> PaginatedRuns:
    """Return one keyset page of run summaries plus the total matching the filters.

    Pages are anchored by an opaque ``cursor`` (the keyset key of the previous
    page's last item) rather than an offset, so newly-created runs at the top of
    the newest-first list never shift an already-fetched page's window.

    Scenario, run-id, and label filters are applied to descriptors before
    enrichment, so the common path (no ``status`` / ``contains_agent_id``
    filter) enriches only the page. ``scenarios`` keeps runs whose scenario is
    in the set (OR semantics; empty means all). ``run_id_contains`` keeps runs
    whose ``scenario/run_dir_name`` id contains the substring (case-insensitive).
    ``knob_filters`` are AND-matched against each run's recorded
    ``scenario_config``, read without enrichment, so they stay on the cheap
    branch. ``status`` and ``contains_agent_id`` depend on enriched fields, so
    when either is set every descriptor-matching candidate is enriched and
    filtered before the page is sliced.
    """
    descriptors = await enumerate_run_descriptors(
        pool=pool,
        runs_dir=runs_dir,
        group_id=group_id,
        scenario_filter=_indexable_scenario(scenarios=scenarios),
    )
    descriptors = await _apply_descriptor_filters(
        descriptors=descriptors,
        runs_dir=runs_dir,
        scenarios=scenarios,
        labels=labels,
        run_id_contains=run_id_contains,
        knob_filters=knob_filters,
    )

    after_key = _decode_cursor(cursor) if cursor is not None else None

    if status is None and contains_agent_id is None:
        # Enforce the total order explicitly so keyset slicing is deterministic
        # regardless of the descriptor source (DB rows or filesystem walk).
        descriptors = sorted(descriptors, key=_descriptor_key, reverse=True)
        total = len(descriptors)
        if after_key is not None:
            descriptors = [d for d in descriptors if _descriptor_key(d) < after_key]
        window = descriptors[:limit]
        has_more = len(descriptors) > limit
        next_cursor = _encode_cursor(_descriptor_key(window[-1])) if has_more and window else None
        page = await _build_summaries(runs_dir=runs_dir, descriptors=window)
        # The page's summaries just read labels.json anyway; repair the rows'
        # labels mirror where a direct file write left it behind.
        await heal_label_mirror(
            pool=pool, group_id=group_id, descriptors=window, summaries=page
        )
        return PaginatedRuns(runs=page, total=total, next_cursor=next_cursor)

    summaries = await _build_summaries(runs_dir=runs_dir, descriptors=descriptors)
    summaries = _apply_enriched_filters(
        summaries=summaries,
        status=status,
        contains_agent_id=contains_agent_id,
    )
    summaries = sorted(summaries, key=_summary_key, reverse=True)
    total = len(summaries)
    if after_key is not None:
        summaries = [s for s in summaries if _summary_key(s) < after_key]
    window_summaries = summaries[:limit]
    has_more = len(summaries) > limit
    next_cursor = (
        _encode_cursor(_summary_key(window_summaries[-1]))
        if has_more and window_summaries
        else None
    )
    # Heal only the returned window, though every candidate was enriched: the
    # descriptor dict covers them all, and the window is the bounded part.
    await heal_label_mirror(
        pool=pool, group_id=group_id, descriptors=descriptors, summaries=window_summaries
    )
    return PaginatedRuns(runs=window_summaries, total=total, next_cursor=next_cursor)


async def list_runs_matching_filters(
    pool: DbPool | None,
    runs_dir: Path,
    group_id: UUID,
    scenarios: list[str],
    labels: list[str],
    run_id_contains: str | None,
    status: RunStatus | None,
    contains_agent_id: str | None,
    knob_filters: list[KnobFilter],
) -> list[RunSummary]:
    """Return every summary matching the runs-list filters, newest-first, unpaginated.

    The filters mean what they mean in :func:`list_runs_page`, because both call
    :func:`_apply_descriptor_filters` for the cheap ones and
    :func:`_apply_enriched_filters` for the rest. What differs is that every
    match is enriched rather than only a page of them, since an export needs the
    full summary of each run it covers.
    """
    descriptors = await enumerate_run_descriptors(
        pool=pool,
        runs_dir=runs_dir,
        group_id=group_id,
        scenario_filter=_indexable_scenario(scenarios=scenarios),
    )
    descriptors = await _apply_descriptor_filters(
        descriptors=descriptors,
        runs_dir=runs_dir,
        scenarios=scenarios,
        labels=labels,
        run_id_contains=run_id_contains,
        knob_filters=knob_filters,
    )
    summaries = await _build_summaries(runs_dir=runs_dir, descriptors=descriptors)
    # Every match just read its labels.json for enrichment, so repair the
    # mirror across all of them, not only a page. Steady-state this plans
    # nothing; it cannot rescue a run a stale mirror already filtered out.
    await heal_label_mirror(
        pool=pool, group_id=group_id, descriptors=descriptors, summaries=summaries
    )
    summaries = _apply_enriched_filters(
        summaries=summaries,
        status=status,
        contains_agent_id=contains_agent_id,
    )
    return sorted(summaries, key=_summary_key, reverse=True)


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


async def list_runs_matching_filters_for_group(
    request: Request,
    scenarios: list[str],
    labels: list[str],
    run_id_contains: str | None,
    status: RunStatus | None,
    contains_agent_id: str | None,
    knob_filters: list[KnobFilter],
) -> list[RunSummary]:
    """REST-layer wrapper around :func:`list_runs_matching_filters`."""
    identity = get_identity(request=request)
    return await list_runs_matching_filters(
        pool=request.app.state.db_pool,
        runs_dir=request.app.state.runs_dir,
        group_id=identity.active_group_id,
        scenarios=scenarios,
        labels=labels,
        run_id_contains=run_id_contains,
        status=status,
        contains_agent_id=contains_agent_id,
        knob_filters=knob_filters,
    )


async def list_runs_page_for_group(
    request: Request,
    scenarios: list[str],
    labels: list[str],
    run_id_contains: str | None,
    status: RunStatus | None,
    contains_agent_id: str | None,
    knob_filters: list[KnobFilter],
    cursor: str | None,
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
        knob_filters=knob_filters,
        cursor=cursor,
        limit=limit,
    )


class _LabelsCacheEntry(NamedTuple):
    """A cached label union with its monotonic expiry timestamp."""

    expires_at: float
    labels: list[str]


# Per-group cache of the label union. The union is derived from one
# ``labels.json`` per run, so computing it is O(runs) filesystem reads; caching
# keeps the (frequently-polled) filter dropdown from re-reading every run's
# labels on each call. Entries are invalidated explicitly on label writes and
# otherwise expire after the TTL.
_LABELS_CACHE: dict[UUID, _LabelsCacheEntry] = {}
_LABELS_CACHE_TTL_SECONDS = 30.0


def invalidate_labels_cache(group_id: UUID) -> None:
    """Drop the cached label union for a group after its labels change."""
    _LABELS_CACHE.pop(group_id, None)


def _read_labels_union_sync(run_dirs: list[Path]) -> list[str]:
    """Read every run's labels.json and return their sorted union (blocking)."""
    seen: set[str] = set()
    for run_dir in run_dirs:
        seen.update(read_run_labels(run_dir=run_dir))
    return sorted(seen)


async def list_all_labels_for_group(request: Request) -> list[str]:
    """Return the sorted union of labels across the active group's runs.

    With Postgres the union is one query over the rows' mirrored labels, no
    cache and no file reads; a deleted run's labels leave the union with its
    row. In no-database local mode every run's ``labels.json`` is read in a
    worker thread, and the union is cached per group with a short TTL so the
    frequently-polled filter dropdown does not re-scan every run on each call.
    """
    identity = get_identity(request=request)
    group_id = identity.active_group_id
    pool = request.app.state.db_pool
    if pool is not None:
        async with pool.connection() as conn:
            return await list_distinct_labels_for_group(conn=conn, group_id=group_id)

    now = time.monotonic()
    cached = _LABELS_CACHE.get(group_id)
    if cached is not None and cached.expires_at > now:
        return cached.labels

    runs_dir: Path = request.app.state.runs_dir
    descriptors = await enumerate_run_descriptors(
        pool=None,
        runs_dir=runs_dir,
        group_id=group_id,
        scenario_filter=None,
    )
    run_dirs = [
        runs_dir / descriptor.scenario_name / descriptor.run_dir_name for descriptor in descriptors
    ]
    labels = await asyncio.to_thread(_read_labels_union_sync, run_dirs)
    _LABELS_CACHE[group_id] = _LabelsCacheEntry(
        expires_at=now + _LABELS_CACHE_TTL_SECONDS,
        labels=labels,
    )
    return labels
