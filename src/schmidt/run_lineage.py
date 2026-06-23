"""Recovers a derived run's timeline parent from its on-disk manifests.

A run created via ``replace-agent``, ``resume-at-round``, or
``cross-run-replace-agent`` records its timeline parent in a manifest file
(``replace_manifest.json`` for the first two, ``cross_run_replace_manifest.json``
for the third — using source A as the timeline parent). This module reads those
manifests back into the ``(scenario, run_dir_name)`` identity the runs index
stores in its ``source_run_scenario`` / ``source_run_dir_name`` columns, so the
import flow can repopulate lineage that would otherwise be lost.
"""

from pathlib import Path
from typing import NamedTuple

from schmidt.cross_run_replace_manifest import read_cross_run_replace_manifest
from schmidt.replace_manifest import read_replace_manifest


class TimelineParent(NamedTuple):
    """A derived run's timeline-parent identity."""

    scenario: str
    run_dir_name: str


def read_timeline_parent(run_dir: Path) -> TimelineParent | None:
    """Return the timeline parent recorded in ``run_dir``'s manifests, else ``None``.

    Cross-run derivations use source A (the timeline parent), matching the
    convention in the runs-index registration path. Returns ``None`` when the
    run carries neither a replace nor a cross-run manifest.
    """
    cross_run_manifest = read_cross_run_replace_manifest(run_dir=run_dir)
    if cross_run_manifest is not None:
        return _split_run_id(run_id=cross_run_manifest.source_a_run_id)

    replace_manifest = read_replace_manifest(run_dir=run_dir)
    if replace_manifest is not None:
        return _split_run_id(run_id=replace_manifest.source_run_id)

    return None


def _split_run_id(run_id: str) -> TimelineParent:
    """Split a ``scenario/run_dir_name`` run id into its two components."""
    scenario, run_dir_name = run_id.split("/", 1)
    return TimelineParent(scenario=scenario, run_dir_name=run_dir_name)
