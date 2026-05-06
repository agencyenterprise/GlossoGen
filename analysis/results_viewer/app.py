"""Streamlit entrypoint: pick between the per-run timeline and the baseline sweep view."""

import os
from pathlib import Path

import streamlit as st

from analysis.results_viewer import (
    baseline_tab,
    cross_swap_tab,
    oss_frontier_tab,
    resume_tab,
    timeline_tab,
    verbosity_tab,
)
from analysis.results_viewer.run_catalog import list_evaluated_runs

st.set_page_config(page_title="Analysis Results Viewer", layout="wide")


def main() -> None:
    """Render six tabs: Timeline, Baseline, Verbosity, Resume, Cross-swap, OSS vs Frontier."""
    runs_dir = Path(os.environ.get("SCHMIDT_RUNS_DIR", "./runs")).resolve()
    st.sidebar.markdown(f"**Runs directory**: `{runs_dir}`")
    evaluated = list_evaluated_runs(runs_dir=runs_dir)
    st.sidebar.markdown(f"**Evaluated runs**: {len(evaluated)}")

    (
        timeline_panel,
        baseline_panel,
        verbosity_panel,
        resume_panel,
        cross_swap_panel,
        oss_frontier_panel,
    ) = st.tabs(["Timeline", "Baseline", "Verbosity", "Resume", "Cross-swap", "OSS vs Frontier"])
    with timeline_panel:
        timeline_tab.render(evaluated=evaluated)
    with baseline_panel:
        baseline_tab.render(evaluated=evaluated)
    with verbosity_panel:
        verbosity_tab.render(evaluated=evaluated)
    with resume_panel:
        resume_tab.render(evaluated=evaluated)
    with cross_swap_panel:
        cross_swap_tab.render(evaluated=evaluated)
    with oss_frontier_panel:
        oss_frontier_tab.render(evaluated=evaluated)


main()
