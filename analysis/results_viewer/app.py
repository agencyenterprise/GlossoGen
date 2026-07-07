"""Streamlit entrypoint: pick between the per-run timeline and the baseline sweep view."""

import os
from pathlib import Path

import streamlit as st

from analysis.results_viewer import (
    baseline_tab,
    container_yard_budget_tab,
    cross_swap_tab,
    feature_presence_tab,
    multi_swap_tab,
    oss_frontier_tab,
    probe_similarity_tab,
    protocol_learnability_tab,
    resume_tab,
    stabilize_overcall_tab,
    timeline_tab,
    verbosity_tab,
)
from analysis.results_viewer.run_catalog import list_evaluated_runs

st.set_page_config(page_title="Analysis Results Viewer", layout="wide")


def main() -> None:
    """Render twelve tabs: Timeline, Baseline, Verbosity, Container-yard budget, Resume, Cross-swap, Multi-swap, OSS-vs-Frontier, Probe similarity, Language features, Protocol learnability, Stabilize over-calling."""  # noqa: E501
    runs_dir = Path(os.environ.get("GLOSSOGEN_RUNS_DIR", "./runs")).resolve()
    st.sidebar.markdown(f"**Runs directory**: `{runs_dir}`")
    evaluated = list_evaluated_runs(runs_dir=runs_dir)
    st.sidebar.markdown(f"**Evaluated runs**: {len(evaluated)}")

    (
        timeline_panel,
        baseline_panel,
        verbosity_panel,
        container_yard_budget_panel,
        resume_panel,
        cross_swap_panel,
        multi_swap_panel,
        oss_frontier_panel,
        probe_similarity_panel,
        feature_presence_panel,
        protocol_learnability_panel,
        stabilize_overcall_panel,
    ) = st.tabs(
        [
            "Timeline",
            "Baseline",
            "Verbosity",
            "Container-yard budget",
            "Resume",
            "Cross-swap",
            "Multi-swap",
            "OSS vs Frontier",
            "Probe similarity",
            "Language features",
            "Protocol learnability",
            "Stabilize over-calling",
        ]
    )
    with timeline_panel:
        timeline_tab.render(evaluated=evaluated)
    with baseline_panel:
        baseline_tab.render(evaluated=evaluated)
    with verbosity_panel:
        verbosity_tab.render(evaluated=evaluated)
    with container_yard_budget_panel:
        container_yard_budget_tab.render(evaluated=evaluated)
    with resume_panel:
        resume_tab.render(evaluated=evaluated)
    with cross_swap_panel:
        cross_swap_tab.render(evaluated=evaluated)
    with multi_swap_panel:
        multi_swap_tab.render(evaluated=evaluated)
    with oss_frontier_panel:
        oss_frontier_tab.render(evaluated=evaluated)
    with probe_similarity_panel:
        probe_similarity_tab.render(evaluated=evaluated)
    with feature_presence_panel:
        feature_presence_tab.render(evaluated=evaluated, runs_dir=runs_dir)
    with protocol_learnability_panel:
        protocol_learnability_tab.render(evaluated=evaluated, runs_dir=runs_dir)
    with stabilize_overcall_panel:
        stabilize_overcall_tab.render(evaluated=evaluated)


main()
