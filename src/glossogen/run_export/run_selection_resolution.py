"""Turning a selection into an ordered list of runs.

Both surfaces reduce to filtering a `list[RunSummary]`, so the filtering itself
lives here once. The server path gets that list from the group-scoped listing; the
CLI path gets it from a filesystem walk. Nothing downstream of this module knows
which one it got.

Runs come out sorted by id, not newest-first. Run ids are unique, so that is
a total order and the same selection puts its rows in the same order every time,
which makes the CSV bytes identical across runs. The archives are not byte-identical
even so: a zip stamps each member with the time it was written.

The list's own newest-first display order is not a total order: two runs claimed in
the same second tie, and their relative position is then whatever the filesystem
returned.
"""

import logging
from typing import NamedTuple

from glossogen.run_export.export_request_models import (
    ExplicitRunSelection,
    FilterRunSelection,
    RunSelection,
)
from glossogen.server.runs.models import RunSummary

logger = logging.getLogger(__name__)


class ResolvedSelection(NamedTuple):
    """The runs a selection names, plus explicit ids that matched nothing."""

    summaries: list[RunSummary]
    missing_run_ids: list[str]


def _matches_filters(summary: RunSummary, selection: FilterRunSelection) -> bool:
    """Return True if one run passes every filter in ``selection``."""
    if selection.scenario and summary.scenario_name not in set(selection.scenario):
        return False
    if selection.run_id_contains:
        if selection.run_id_contains.lower() not in summary.run_id.lower():
            return False
    if selection.status is not None and summary.status != selection.status:
        return False
    if selection.labels:
        if not set(selection.labels).issubset(set(summary.labels)):
            return False
    if selection.contains_agent_id is not None:
        registered = {agent.agent_id for agent in summary.agent_models}
        if selection.contains_agent_id not in registered:
            return False
    return True


def _sorted_by_run_id(summaries: list[RunSummary]) -> list[RunSummary]:
    """Return the runs in ascending run-id order."""
    return sorted(summaries, key=lambda summary: summary.run_id)


def partition_explicit_run_ids(
    run_ids: list[str],
    owned_by_run_id: dict[str, RunSummary],
) -> ResolvedSelection:
    """Split requested ids into runs that resolve and ids that do not.

    Duplicates collapse. An id naming a run this caller cannot see comes back in
    ``missing_run_ids`` for the surface above to act on, since a row dropped here would
    leave no trace in the export.
    """
    seen: set[str] = set()
    found: list[RunSummary] = []
    missing: list[str] = []
    for run_id in run_ids:
        if run_id in seen:
            continue
        seen.add(run_id)
        summary = owned_by_run_id.get(run_id)
        if summary is None:
            missing.append(run_id)
            continue
        found.append(summary)
    return ResolvedSelection(summaries=_sorted_by_run_id(found), missing_run_ids=missing)


def resolve_selection(
    candidates: list[RunSummary],
    selection: RunSelection,
) -> ResolvedSelection:
    """Resolve ``selection`` against every run the caller can see."""
    if isinstance(selection, ExplicitRunSelection):
        return partition_explicit_run_ids(
            run_ids=selection.run_ids,
            owned_by_run_id={summary.run_id: summary for summary in candidates},
        )
    matched = [
        summary for summary in candidates if _matches_filters(summary=summary, selection=selection)
    ]
    return ResolvedSelection(summaries=_sorted_by_run_id(matched), missing_run_ids=[])
