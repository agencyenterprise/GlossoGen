"""Streamlit slider that filters runs by stabilization-judge replay damage.

Each veyru run carries a ``judge_replay.json`` sidecar with the ratio of
previously-accepted ``stabilize_veyru`` actions that flip to rejected under
the current judge prompt. This module exposes a slider widget (0-100%) that
gates which runs are visible in a tab: the slider value is the MAXIMUM
flip-ratio a run may have to be shown.

- Slider at 100% -> every run passes (any flip ratio up to 100% is allowed).
- Slider at 0%   -> only runs with zero flips pass (the "clean" cohort).

Runs without a sidecar (non-veyru or never replayed) are treated as if their
flip ratio were 0, so they always pass the filter - the slider is purely a
veyru damage gate, not a "has a sidecar" gate.

Two public callables:

- ``flip_ratio_by_run_id(evaluated)`` builds the ``run_id -> flip_ratio``
  lookup once at the top of a tab, while the run set is still the unfiltered
  ``EvaluatedRun`` list.
- ``render_and_filter(items, ratio_of, key, item_label)`` renders the slider
  widget at the call site (so each tab can place it directly above its plot)
  and returns the filtered item list. ``ratio_of`` is a callable that maps
  each item to its flip ratio or ``None``. ``item_label`` is the noun shown
  in the count caption (defaults to "runs").
"""

from typing import Callable, TypeVar

import streamlit as st

from analysis.results_viewer.run_catalog import EvaluatedRun

T = TypeVar("T")


def flip_ratio_by_run_id(evaluated: list[EvaluatedRun]) -> dict[str, float | None]:
    """Build a ``run_id -> flip_ratio`` lookup so downstream items can resolve their ratio."""
    return {run.run_id: run.judge_replay_flip_ratio for run in evaluated}


def render_and_filter(
    items: list[T],
    ratio_of: Callable[[T], float | None],
    key: str,
    item_label: str,
) -> list[T]:
    """Render the judge-replay slider, return ``items`` filtered to ratio <= threshold.

    Items whose ratio is ``None`` (no sidecar) always pass. ``key`` must be
    unique per tab/subtab so each slider keeps its own widget state. The
    slider always renders when ``items`` is non-empty so the user can see
    and discover it; if none of the items has a sidecar, sliding is a no-op
    and the caption notes the absence of coverage.
    """
    if not items:
        return items
    relevant_ratios = [ratio_of(item) for item in items if ratio_of(item) is not None]
    damaged_count = sum(1 for r in relevant_ratios if r is not None and r > 0)
    threshold_pct = st.slider(
        "Max judge-replay flip rate per run (%)",
        min_value=0,
        max_value=100,
        value=100,
        step=1,
        help=(
            "Filter out veyru runs whose previously-accepted stabilizations were "
            "over-credited by the original judge. 100% shows everything; 0% keeps "
            "only runs with zero flips. Items without a sidecar always pass."
        ),
        key=f"judge_replay_threshold_{key}",
    )
    threshold = threshold_pct / 100.0
    filtered: list[T] = []
    for item in items:
        ratio = ratio_of(item)
        if ratio is None or ratio <= threshold:
            filtered.append(item)
    excluded = len(items) - len(filtered)
    if not relevant_ratios:
        st.caption(
            f"Judge-replay slider at {threshold_pct}% - none of the {len(items):,} "
            f"{item_label} in scope have a `judge_replay.json` sidecar, so the slider is "
            f"a no-op here (sidecars are only generated for veyru runs)."
        )
    elif excluded > 0:
        st.warning(
            f"**{excluded:,}** of {len(items):,} {item_label} filtered out by judge-replay "
            f"slider (threshold <= {threshold_pct}%). {len(filtered):,} remain. "
            f"Sidecar coverage: {len(relevant_ratios):,} {item_label}, "
            f"{damaged_count:,} with >= 1 flip."
        )
    else:
        st.caption(
            f"Judge-replay slider at {threshold_pct}% - 0 {item_label} filtered out, "
            f"{len(filtered):,} visible. Sidecar coverage: {len(relevant_ratios):,} "
            f"{item_label}, {damaged_count:,} with >= 1 flip."
        )
    return filtered
