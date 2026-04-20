"""Streamlit entrypoint: pick evaluated Veyru runs, render an overlay timeline."""

import os
from pathlib import Path

import streamlit as st

from analysis.results_viewer.event_extractor import load_run_timeline
from analysis.results_viewer.run_catalog import EvaluatedRun, list_evaluated_runs
from analysis.results_viewer.timeline_plot import (
    build_timeline_figure,
    collect_per_round_evaluators,
)

st.set_page_config(page_title="Veyru Timeline", layout="wide")


def _describe(run: EvaluatedRun) -> str:
    """Multiselect label combining timestamp, run_id, and mode."""
    return run.label


def main() -> None:
    """Render the timeline viewer."""
    runs_dir = Path(os.environ.get("SCHMIDT_RUNS_DIR", "./runs")).resolve()
    st.sidebar.markdown(f"**Runs directory**: `{runs_dir}`")
    evaluated = list_evaluated_runs(runs_dir=runs_dir)
    st.sidebar.markdown(f"**Evaluated runs**: {len(evaluated)}")

    if not evaluated:
        st.info("No evaluated Veyru runs found. Run `schmidt evaluate veyru --run-dir ...` first.")
        return

    default_selection = evaluated[: min(2, len(evaluated))]
    selected = st.multiselect(
        label="Runs to overlay",
        options=evaluated,
        default=default_selection,
        format_func=_describe,
        key="runs_picker",
    )
    if not selected:
        st.info("Pick at least one run.")
        return

    reports = {run.label: run.report for run in selected}
    timelines = {run.label: load_run_timeline(run_dir=run.run_dir) for run in selected}

    available_evaluators = collect_per_round_evaluators(reports=list(reports.values()))
    if not available_evaluators:
        st.info("None of the selected runs have evaluators that report per-round evidence.")
        return
    chosen_evaluators = st.multiselect(
        label="Evaluators to show",
        options=available_evaluators,
        default=available_evaluators,
        key="evaluators_picker",
    )
    fig = build_timeline_figure(reports=reports, timelines=timelines, evaluators=chosen_evaluators)
    st.plotly_chart(fig, width="stretch")

    with st.expander("Selected runs — scenario config", expanded=False):
        for run in selected:
            st.markdown(f"**{run.label}**")
            st.json(timelines[run.label].scenario_config)


main()
