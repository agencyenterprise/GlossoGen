"""Streamlit entrypoint: pick evaluated Veyru runs, render overlay or compact timelines."""

import os
from datetime import datetime
from pathlib import Path

import pyperclip
import streamlit as st

from analysis.results_viewer.event_extractor import load_run_timeline
from analysis.results_viewer.run_catalog import EvaluatedRun, group_runs_by_day, list_evaluated_runs
from analysis.results_viewer.timeline_plot import (
    build_timeline_figure,
    collect_per_round_evaluators,
    palette_color_for_index,
)
from schmidt.evaluation.evaluation_report import EvaluationReport, MetricResult

st.set_page_config(page_title="Veyru Timeline", layout="wide")


def _render_checkbox_filter(
    container: st.delta_generator.DeltaGenerator,
    title: str,
    options_with_counts: list[tuple[str, int]],
    key_prefix: str,
) -> set[str]:
    """Render a vertical checkbox list inside ``container``; return the checked option names."""
    container.markdown(f"**{title}**")
    if not options_with_counts:
        container.caption("None available.")
        return set()
    selected: set[str] = set()
    for name, count in options_with_counts:
        checked = container.checkbox(
            label=f"{name} ({count})",
            value=True,
            key=f"{key_prefix}::{name}",
        )
        if checked:
            selected.add(name)
    return selected


def _render_prefilters(runs: list[EvaluatedRun]) -> tuple[set[str], set[str]]:
    """Side-by-side pre-filters for execution mode and model, above the run picker."""
    mode_counts: dict[str, int] = {}
    model_counts: dict[str, int] = {}
    for run in runs:
        mode_counts[run.execution_mode] = mode_counts.get(run.execution_mode, 0) + 1
        model = run.metadata.primary_model
        model_counts[model] = model_counts.get(model, 0) + 1
    modes_sorted = sorted(mode_counts.items())
    models_sorted = sorted(model_counts.items())
    mode_col, model_col = st.columns(2)
    selected_modes = _render_checkbox_filter(
        container=mode_col,
        title="Execution mode",
        options_with_counts=modes_sorted,
        key_prefix="execution_mode_filter",
    )
    selected_models = _render_checkbox_filter(
        container=model_col,
        title="Model",
        options_with_counts=models_sorted,
        key_prefix="model_filter",
    )
    return selected_modes, selected_models


def _format_run_option(run: EvaluatedRun) -> str:
    """Dropdown label with the day prefix so runs visually cluster by date."""
    day_prefix = datetime.fromtimestamp(run.run_timestamp).strftime("%a %b %d")
    return f"{day_prefix} · {run.label}"


def _render_run_picker(runs: list[EvaluatedRun]) -> list[EvaluatedRun]:
    """Single multiselect dropdown; options are ordered by day (newest first)."""
    if not runs:
        st.info("No runs match the current model filter.")
        return []
    grouped = group_runs_by_day(runs=runs)
    ordered: list[EvaluatedRun] = []
    for group in grouped:
        ordered.extend(group.runs)
    st.markdown("### Runs to overlay")
    return st.multiselect(
        label="Pick runs to overlay (grouped by day)",
        options=ordered,
        default=[],
        format_func=_format_run_option,
        key="runs_picker",
        label_visibility="collapsed",
        max_selections=10,
    )


def _find_metric(report: EvaluationReport, evaluator_name: str) -> MetricResult | None:
    """Return the first metric matching ``evaluator_name`` in ``report``."""
    for metric in report.metrics:
        if metric.evaluator_name == evaluator_name:
            return metric
    return None


@st.dialog("Evaluator output", width="large", on_dismiss="rerun")
def _show_evaluator_dialog(
    run_label: str, evaluator_name: str, round_number: int, report: EvaluationReport
) -> None:
    """Modal showing the evaluator's verdict/score/evidence for a clicked point."""
    metric = _find_metric(report=report, evaluator_name=evaluator_name)
    st.markdown(f"**Run** · {run_label}")
    st.markdown(f"**Evaluator** · {evaluator_name}")
    st.markdown(f"**Round** · {round_number}")
    if metric is None:
        st.warning("No metric found for this evaluator in the selected run.")
        return
    st.markdown(f"**Verdict** · `{metric.verdict.value}`")
    st.markdown(f"**Score** · {metric.score}")
    st.markdown("**Evidence**")
    if metric.evidence:
        for line in metric.evidence:
            st.markdown(f"- {line}")
    else:
        st.caption("No evidence recorded.")
    if metric.per_agent:
        st.markdown("**Per-agent verdicts**")
        for agent_id, verdict in metric.per_agent.items():
            st.markdown(f"- `{agent_id}` · {verdict.value}")


def _timeline_chart_key() -> str:
    """Chart key whose revision suffix flips after every click.

    Bumping the revision after showing the modal remounts the widget on the next rerun,
    discarding Plotly's retained selection so the very next click — even on the same
    point — fires a fresh selection event and reopens the modal.
    """
    return f"timeline_chart::{st.session_state.get('timeline_chart_rev', 0)}"


def _maybe_open_point_modal(selection_state: object, reports: dict[str, EvaluationReport]) -> None:
    """Open the evaluator dialog on a click; bump the chart revision to reset selection."""
    points = getattr(getattr(selection_state, "selection", None), "points", None)
    if not points:
        return
    first = points[0]
    customdata = first.get("customdata")
    if not customdata or len(customdata) < 3:
        return
    run_label = str(customdata[0])
    evaluator_name = str(customdata[1])
    round_number = int(customdata[2])
    report = reports.get(run_label)
    if report is None:
        return
    st.session_state["timeline_chart_rev"] = st.session_state.get("timeline_chart_rev", 0) + 1
    _show_evaluator_dialog(
        run_label=run_label,
        evaluator_name=evaluator_name,
        round_number=round_number,
        report=report,
    )


def _render_run_id_copy_chip(run_id: str) -> None:
    """Button showing the run id's first 8 chars; click copies the full UUID via pyperclip.

    ``pyperclip`` writes to the machine running the Streamlit server, which — in this
    local-only viewer — is the same machine the user is on, so the UUID lands in the
    user's clipboard.
    """
    short = run_id[:8]
    if st.button(
        label=f"{short} ⧉",
        key=f"copy_run_id::{run_id}",
        help=f"Copy run id: {run_id}",
    ):
        pyperclip.copy(run_id)
        st.toast(f"Copied {run_id}")


def _render_selected_run_links(runs: list[EvaluatedRun]) -> None:
    """Render one row per selected run with colour swatch, run id (copy-able) and detail link.

    The colour swatch matches the palette colour ``build_timeline_figure`` assigns to the
    same run, so rows line up visually with their lines/dots on the timeline.
    """
    frontend_base = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    st.markdown("### Selected runs")
    for index, run in enumerate(runs):
        detail_url = f"{frontend_base}/runs/{run.run_id}"
        colour = palette_color_for_index(index=index)
        swatch_col, label_col, id_col, link_col = st.columns([0.3, 4, 2, 1])
        swatch_col.markdown(
            f"<div style='width:1rem;height:1rem;border-radius:50%;"
            f"background:{colour};margin-top:0.4rem;'></div>",
            unsafe_allow_html=True,
        )
        label_col.markdown(run.label)
        with id_col:
            _render_run_id_copy_chip(run_id=run.run_id)
        link_col.markdown(f"[Open ↗]({detail_url})")


_EVALUATOR_CHECKBOXES_PER_ROW = 4


def _render_evaluator_checkboxes(available: list[str]) -> list[str]:
    """Render evaluator checkboxes, wrapping to new rows so long names stay readable."""
    st.markdown("### Evaluators")
    chosen: list[str] = []
    for row_start in range(0, len(available), _EVALUATOR_CHECKBOXES_PER_ROW):
        row_items = available[row_start : row_start + _EVALUATOR_CHECKBOXES_PER_ROW]
        cols = st.columns(_EVALUATOR_CHECKBOXES_PER_ROW)
        for col_index, name in enumerate(row_items):
            if cols[col_index].checkbox(label=name, value=True, key=f"eval_select::{name}"):
                chosen.append(name)
    return chosen


def main() -> None:
    """Render the timeline viewer."""
    runs_dir = Path(os.environ.get("SCHMIDT_RUNS_DIR", "./runs")).resolve()
    st.sidebar.markdown(f"**Runs directory**: `{runs_dir}`")
    evaluated = list_evaluated_runs(runs_dir=runs_dir)
    st.sidebar.markdown(f"**Evaluated runs**: {len(evaluated)}")

    if not evaluated:
        st.info("No evaluated Veyru runs found. Run `schmidt evaluate veyru --run-dir ...` first.")
        return

    selected_modes, selected_models = _render_prefilters(runs=evaluated)
    filtered = [
        run
        for run in evaluated
        if run.execution_mode in selected_modes and run.metadata.primary_model in selected_models
    ]

    selected = _render_run_picker(runs=filtered)
    if not selected:
        st.info("Pick at least one run.")
        return

    _render_selected_run_links(runs=selected)

    reports = {run.label: run.report for run in selected}
    timelines = {run.label: load_run_timeline(run_dir=run.run_dir) for run in selected}

    available_evaluators = collect_per_round_evaluators(reports=list(reports.values()))
    if not available_evaluators:
        st.info("None of the selected runs have evaluators that report per-round evidence.")
        return

    chosen_evaluators = _render_evaluator_checkboxes(available=available_evaluators)
    if not chosen_evaluators:
        st.info("Select at least one evaluator.")
        return

    fig = build_timeline_figure(
        reports=reports,
        timelines=timelines,
        evaluators=chosen_evaluators,
    )
    selection_state = st.plotly_chart(
        fig,
        width="stretch",
        on_select="rerun",
        selection_mode=("points",),
        key=_timeline_chart_key(),
    )
    _maybe_open_point_modal(selection_state=selection_state, reports=reports)

    with st.expander("Selected runs — scenario config", expanded=False):
        for run in selected:
            st.markdown(f"**{run.label}**")
            st.json(timelines[run.label].scenario_config)


main()
