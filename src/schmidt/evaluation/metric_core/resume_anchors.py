"""Helpers for locating swap boundaries in resumed / in-run-swap simulations.

The platform's ``round_success_after_resume`` metric (and any future
"after a swap" metric) needs to know:

* Which rounds in the current log were played after a swap boundary
  (the "resumed window").
* Which rounds form the comparison baseline — either the same window
  in a different source run (for the replace-agent / cross-run flows)
  or an earlier window in the same run (for in-run scheduled swaps).

This module reads the three manifest types (``replace_manifest.json``,
``cross_run_replace_manifest.json``, ``AgentSwappedMidRun`` events) and
returns a uniform ``ResumeAnchor`` per swap boundary so downstream
metrics do not have to special-case the three flows.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from schmidt.cross_run_replace_manifest import read_cross_run_replace_manifest
from schmidt.models.event import AgentSwappedMidRun, RoundAdvanced, SimulationEvent
from schmidt.replace_manifest import read_replace_manifest

logger = logging.getLogger(__name__)


class ResumeAnchor(NamedTuple):
    """One swap boundary's resumed window plus its comparison baseline.

    ``round_start`` and ``rounds_after_swap`` define the inclusive
    resumed window ``[round_start, round_start + rounds_after_swap]``.
    For manifest flows the baseline lives in a different run
    (``external_source_run_id`` / ``external_source_run_dir``); for
    in-run scheduled flows the baseline window is in the same run
    (``in_run_baseline_window``). Exactly one of the two baseline
    fields is populated.

    ``flow_label`` is rendered into measurement summary text.
    ``replaced_agent_id`` is set for in-run scheduled flows so
    multiple anchors in one run can produce distinct measurement
    names.
    """

    round_start: int
    rounds_after_swap: int
    flow_label: str
    external_source_run_id: str | None
    external_source_run_dir: str | None
    in_run_baseline_window: tuple[int, int] | None
    replaced_agent_id: str | None


def read_resume_anchors(events: list[SimulationEvent], run_dir: Path) -> list[ResumeAnchor]:
    """Return one ``ResumeAnchor`` per swap boundary in the run.

    Order of precedence: in-run ``AgentSwappedMidRun`` events first
    (one anchor per event); falling back to ``replace_manifest.json``
    or ``cross_run_replace_manifest.json`` only when no swap events
    were logged. The returned list preserves declaration order, which
    matches ascending ``round_number`` for in-run scheduled flows.
    """
    in_run_anchors = _collect_in_run_anchors(events=events)
    if in_run_anchors:
        return in_run_anchors
    replace = read_replace_manifest(run_dir=run_dir)
    if replace is not None:
        return [
            ResumeAnchor(
                round_start=replace.round_start,
                rounds_after_swap=replace.rounds_after_swap,
                flow_label="replace-agent",
                external_source_run_id=replace.source_run_id,
                external_source_run_dir=replace.source_run_dir,
                in_run_baseline_window=None,
                replaced_agent_id=None,
            )
        ]
    cross_run = read_cross_run_replace_manifest(run_dir=run_dir)
    if cross_run is not None:
        return [
            ResumeAnchor(
                round_start=cross_run.round_start,
                rounds_after_swap=cross_run.rounds_after_swap,
                flow_label="cross-run replace-agent",
                external_source_run_id=cross_run.source_a_run_id,
                external_source_run_dir=cross_run.source_a_run_dir,
                in_run_baseline_window=None,
                replaced_agent_id=None,
            )
        ]
    return []


def collect_advanced_round_numbers(events: list[SimulationEvent]) -> set[int]:
    """Return every round number that actually advanced in the log."""
    return {event.round_number for event in events if isinstance(event, RoundAdvanced)}


def resolve_external_source_dir(source_run_dir: str) -> Path | None:
    """Return the source run directory, trying the stored path then cwd-relative."""
    raw_path = Path(source_run_dir)
    if raw_path.is_dir():
        return raw_path
    cwd_relative = Path.cwd() / source_run_dir
    if cwd_relative.is_dir():
        return cwd_relative
    return None


def candidate_rounds(anchor: ResumeAnchor) -> set[int]:
    """Inclusive ``[round_start, round_start + rounds_after_swap]`` round set."""
    return set(range(anchor.round_start, anchor.round_start + anchor.rounds_after_swap + 1))


def anchor_metric_name(base_name: str, anchor: ResumeAnchor) -> str:
    """Build a metric name with a per-anchor suffix for in-run scheduled swaps.

    Manifest-based anchors keep ``base_name`` unchanged so existing
    consumers continue to work. In-run scheduled anchors append
    ``_round_<R>_<agent_id>`` so multiple anchors in the same run do
    not collide on measurement name.
    """
    if anchor.replaced_agent_id is None:
        return base_name
    return f"{base_name}_round_{anchor.round_start}_{anchor.replaced_agent_id}"


def _collect_in_run_anchors(events: list[SimulationEvent]) -> list[ResumeAnchor]:
    """Build one anchor per ``AgentSwappedMidRun`` event.

    Each anchor's resumed window runs from its swap round to one round
    before the next swap (or to the last advanced round of the run).
    Its in-run baseline window is the slice between the previous swap
    (or round 1) and the current swap.
    """
    swaps = [event for event in events if isinstance(event, AgentSwappedMidRun)]
    if not swaps:
        return []
    advanced_rounds = collect_advanced_round_numbers(events=events)
    if not advanced_rounds:
        return []
    last_round = max(advanced_rounds)

    anchors: list[ResumeAnchor] = []
    swap_rounds_sorted = sorted(swap.round_number for swap in swaps)
    for index, swap in enumerate(swaps):
        next_index = swap_rounds_sorted.index(swap.round_number) + 1
        if next_index < len(swap_rounds_sorted):
            window_end = swap_rounds_sorted[next_index] - 1
        else:
            window_end = last_round
        rounds_after_swap = max(0, window_end - swap.round_number)

        if index == 0:
            baseline_start = 1
        else:
            baseline_start = swaps[index - 1].round_number
        baseline_end = swap.round_number - 1
        baseline_window: tuple[int, int] | None
        if baseline_end >= baseline_start:
            baseline_window = (baseline_start, baseline_end)
        else:
            baseline_window = None

        anchors.append(
            ResumeAnchor(
                round_start=swap.round_number,
                rounds_after_swap=rounds_after_swap,
                flow_label="in-run scheduled swap",
                external_source_run_id=None,
                external_source_run_dir=None,
                in_run_baseline_window=baseline_window,
                replaced_agent_id=swap.agent_id,
            )
        )
    return anchors
