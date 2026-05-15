"""Shared streamlit helper: radio selector + filter for seed mode (random vs fixed).

Runs launched with a single canonical seed (e.g. seed=42) measure model
stochasticity on identical workloads, while runs launched with random
per-launch seeds also pull workload variance into the estimate. Some
analyses make sense only on one of those cohorts, so every tab gets a
radio to filter the loaded evaluated runs by the ``random_seed`` label.
"""

from typing import Literal

import streamlit as st

from analysis.results_viewer.measurement_scores import read_labels
from analysis.results_viewer.run_catalog import EvaluatedRun

SeedMode = Literal["all", "random", "fixed"]

RANDOM_SEED_LABEL = "random_seed"

_RADIO_OPTIONS: tuple[tuple[SeedMode, str], ...] = (
    ("all", "All"),
    ("random", "Random seed"),
    ("fixed", "Fixed seed"),
)


def render_radio(key_prefix: str) -> SeedMode:
    """Render the seed-mode radio and return the selected mode.

    ``key_prefix`` must be unique per tab to avoid Streamlit widget-key
    collisions across tabs that share this helper.
    """
    labels = [label for _, label in _RADIO_OPTIONS]
    chosen = st.radio(
        label="Seed mode",
        options=labels,
        index=0,
        horizontal=True,
        key=f"{key_prefix}_seed_mode_radio",
        help=(
            "Filter loaded runs by the `random_seed` label. "
            "'Random seed' keeps only runs labeled `random_seed`; "
            "'Fixed seed' keeps only runs without that label."
        ),
    )
    for mode, label in _RADIO_OPTIONS:
        if label == chosen:
            return mode
    return "all"


def apply(evaluated: list[EvaluatedRun], mode: SeedMode) -> list[EvaluatedRun]:
    """Filter ``evaluated`` to runs matching the selected seed mode."""
    if mode == "all":
        return evaluated
    if mode == "random":
        return [r for r in evaluated if RANDOM_SEED_LABEL in read_labels(run_dir=r.run_dir)]
    return [r for r in evaluated if RANDOM_SEED_LABEL not in read_labels(run_dir=r.run_dir)]
