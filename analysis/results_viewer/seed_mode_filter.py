"""Shared streamlit helper: label-based checkbox filters for run cohorts.

Two dimensions:
  * Seed mode — ``random_seed`` label present (random per-launch seed) vs
    absent (canonical fixed seed).
  * Easy-round skeleton — ``no_ordered_easy_rounds`` label present
    (rounds 1/2/3/6/13 are not forced single-stage) vs absent (the
    default warmup skeleton).

Each dimension is exposed as a pair of checkboxes (both checked by
default, equivalent to no filter). Unchecking a checkbox removes that
slice of runs from the loaded set.
"""

from typing import NamedTuple

import streamlit as st

from analysis.results_viewer.measurement_scores import read_labels
from analysis.results_viewer.run_catalog import EvaluatedRun

RANDOM_SEED_LABEL = "random_seed"
NO_ORDERED_EASY_ROUNDS_LABEL = "no_ordered_easy_rounds"


class RunFilter(NamedTuple):
    """Per-tab filter state from the seed + easy-rounds checkboxes."""

    include_random_seed: bool
    include_fixed_seed: bool
    include_no_ordered_easy_rounds: bool
    include_ordered_easy_rounds: bool


def render_filters(key_prefix: str) -> RunFilter:
    """Render the two-dimensional cohort filter section and return its state.

    ``key_prefix`` must be unique per tab to avoid Streamlit widget-key
    collisions across tabs that share this helper.
    """
    cols = st.columns([3, 3])
    with cols[0]:
        st.caption("Seed")
        seed_cols = st.columns(2)
        with seed_cols[0]:
            random_seed = st.checkbox(
                label="Random seed",
                value=True,
                key=f"{key_prefix}_filter_random_seed",
                help="Include runs labeled `random_seed` (per-launch random seed).",
            )
        with seed_cols[1]:
            fixed_seed = st.checkbox(
                label="Fixed seed",
                value=True,
                key=f"{key_prefix}_filter_fixed_seed",
                help="Include runs without the `random_seed` label (canonical fixed seed).",
            )
    with cols[1]:
        st.caption("Easy rounds")
        easy_cols = st.columns(2)
        with easy_cols[0]:
            no_easy = st.checkbox(
                label="No ordered easy rounds",
                value=True,
                key=f"{key_prefix}_filter_no_ordered_easy_rounds",
                help=(
                    "Include runs labeled `no_ordered_easy_rounds` "
                    "(easy_round_numbers=[] — no fixed warmup skeleton)."
                ),
            )
        with easy_cols[1]:
            with_easy = st.checkbox(
                label="Ordered easy rounds",
                value=True,
                key=f"{key_prefix}_filter_ordered_easy_rounds",
                help=(
                    "Include runs without the `no_ordered_easy_rounds` label "
                    "(default rounds 1/2/3/6/13 are forced single-stage)."
                ),
            )
    return RunFilter(
        include_random_seed=random_seed,
        include_fixed_seed=fixed_seed,
        include_no_ordered_easy_rounds=no_easy,
        include_ordered_easy_rounds=with_easy,
    )


def apply(evaluated: list[EvaluatedRun], run_filter: RunFilter) -> list[EvaluatedRun]:
    """Filter ``evaluated`` based on the seed + easy-rounds checkbox state."""
    out: list[EvaluatedRun] = []
    for r in evaluated:
        labels = read_labels(run_dir=r.run_dir)
        has_random = RANDOM_SEED_LABEL in labels
        if has_random and not run_filter.include_random_seed:
            continue
        if not has_random and not run_filter.include_fixed_seed:
            continue
        has_no_easy = NO_ORDERED_EASY_ROUNDS_LABEL in labels
        if has_no_easy and not run_filter.include_no_ordered_easy_rounds:
            continue
        if not has_no_easy and not run_filter.include_ordered_easy_rounds:
            continue
        out.append(r)
    return out
