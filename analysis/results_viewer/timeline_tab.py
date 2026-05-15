"""Streamlit tab rendering the per-run timeline overlay."""

import os
from datetime import datetime

import pyperclip
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from analysis.results_viewer.event_extractor import load_run_timeline
from analysis.results_viewer.run_catalog import EvaluatedRun, group_runs_by_day
from analysis.results_viewer.timeline_plot import (
    build_timeline_figure,
    build_value_metrics_figure,
    collect_flag_metrics,
    collect_value_metrics,
    palette_color_for_index,
)
from analysis.results_viewer import seed_mode_filter
from schmidt.evaluation.metric_core.measurement import Measurement
from schmidt.evaluation.reports.evaluation_report import EvaluationReport

_METRIC_CHECKBOXES_PER_ROW = 4


def _render_checkbox_filter(
    container: DeltaGenerator,
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


def _scenarios_with_evaluated_runs(evaluated: list[EvaluatedRun]) -> list[str]:
    """Return every scenario that has at least one evaluated run."""
    return sorted({run.scenario_name for run in evaluated})


def _render_scenario_selector(evaluated: list[EvaluatedRun]) -> str | None:
    """Radio selector listing every scenario with evaluated runs."""
    options = _scenarios_with_evaluated_runs(evaluated=evaluated)
    if not options:
        return None
    chosen = st.radio(
        label="Scenario",
        options=options,
        index=0,
        horizontal=True,
        key="timeline_scenario_selector",
    )
    return chosen


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


def _find_measurement(report: EvaluationReport, metric_name: str) -> Measurement | None:
    """Return the first measurement matching ``metric_name`` in ``report``."""
    for measurement in report.measurements:
        if measurement.metric_name == metric_name:
            return measurement
    return None


@st.dialog("Metric output", width="large", on_dismiss="rerun")
def _show_metric_dialog(
    run_label: str, metric_name: str, round_number: int, report: EvaluationReport
) -> None:
    """Modal showing the metric's score/summary/per-round detail for a clicked point."""
    measurement = _find_measurement(report=report, metric_name=metric_name)
    st.markdown(f"**Run** · {run_label}")
    st.markdown(f"**Metric** · {metric_name}")
    st.markdown(f"**Round** · {round_number}")
    if measurement is None:
        st.warning("No measurement found for this metric in the selected run.")
        return
    st.markdown(f"**Score** · {measurement.score} ({measurement.score_unit})")
    st.markdown(f"**Summary** · {measurement.summary}")
    matched = [r for r in measurement.per_round if r.round_number == round_number]
    if matched:
        st.markdown("**This round**")
        for round_obs in matched:
            st.markdown(f"- value={round_obs.value} — {round_obs.note}")
    if measurement.per_round:
        st.markdown("**All flagged rounds**")
        for round_obs in measurement.per_round:
            st.markdown(
                f"- round {round_obs.round_number}: value={round_obs.value} — {round_obs.note}"
            )
    if measurement.per_agent:
        st.markdown("**Per-agent observations**")
        for agent_obs in measurement.per_agent:
            st.markdown(f"- `{agent_obs.agent_id}` · value={agent_obs.value} — {agent_obs.note}")


def _timeline_chart_key() -> str:
    """Chart key whose revision suffix flips after every click.

    Bumping the revision after showing the modal remounts the widget on the next rerun,
    discarding Plotly's retained selection so the very next click — even on the same
    point — fires a fresh selection event and reopens the modal.
    """
    return f"timeline_chart::{st.session_state.get('timeline_chart_rev', 0)}"


def _maybe_open_point_modal(selection_state: object, reports: dict[str, EvaluationReport]) -> None:
    """Open the metric dialog on a click; bump the chart revision to reset selection."""
    points = getattr(getattr(selection_state, "selection", None), "points", None)
    if not points:
        return
    first = points[0]
    customdata = first.get("customdata")
    if not customdata or len(customdata) < 3:
        return
    run_label = str(customdata[0])
    metric_name = str(customdata[1])
    round_number = int(customdata[2])
    report = reports.get(run_label)
    if report is None:
        return
    st.session_state["timeline_chart_rev"] = st.session_state.get("timeline_chart_rev", 0) + 1
    _show_metric_dialog(
        run_label=run_label,
        metric_name=metric_name,
        round_number=round_number,
        report=report,
    )


def _render_run_id_copy_chip(run_id: str) -> None:
    """Button showing the run's directory name; click copies the full run id.

    Run IDs have the form ``{scenario}/{dir_name}``; the chip shows just the
    directory name since the scenario is already implied by the enclosing UI
    context. ``pyperclip`` writes to the machine running the Streamlit server,
    which — in this local-only viewer — is the same machine the user is on, so
    the id lands in the user's clipboard.
    """
    short = run_id.split("/")[-1]
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


def _render_metric_checkboxes(available: list[str]) -> list[str]:
    """Render flag-metric checkboxes, wrapping rows so long names stay readable."""
    chosen: list[str] = []
    for row_start in range(0, len(available), _METRIC_CHECKBOXES_PER_ROW):
        row_items = available[row_start : row_start + _METRIC_CHECKBOXES_PER_ROW]
        cols = st.columns(_METRIC_CHECKBOXES_PER_ROW)
        for col_index, name in enumerate(row_items):
            if cols[col_index].checkbox(label=name, value=True, key=f"flag_select::{name}"):
                chosen.append(name)
    return chosen


def _render_value_metric_checkboxes(available: list[str]) -> list[str]:
    """Render value-metric checkboxes; uses a separate state namespace from flag selectors."""
    chosen: list[str] = []
    for row_start in range(0, len(available), _METRIC_CHECKBOXES_PER_ROW):
        row_items = available[row_start : row_start + _METRIC_CHECKBOXES_PER_ROW]
        cols = st.columns(_METRIC_CHECKBOXES_PER_ROW)
        for col_index, name in enumerate(row_items):
            if cols[col_index].checkbox(label=name, value=True, key=f"value_select::{name}"):
                chosen.append(name)
    return chosen


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Timeline tab body."""
    seed_mode = seed_mode_filter.render_radio(key_prefix="timeline")
    evaluated = seed_mode_filter.apply(evaluated=evaluated, mode=seed_mode)
    if not evaluated:
        st.info("No evaluated runs found. Run `schmidt evaluate <scenario> --run-dir ...` first.")
        return

    scenario_name = _render_scenario_selector(evaluated=evaluated)
    if scenario_name is None:
        st.info("No evaluated runs found.")
        return
    scenario_runs = [run for run in evaluated if run.scenario_name == scenario_name]

    selected_modes, selected_models = _render_prefilters(runs=scenario_runs)
    filtered = [
        run
        for run in scenario_runs
        if run.execution_mode in selected_modes and run.metadata.primary_model in selected_models
    ]

    selected = _render_run_picker(runs=filtered)
    if not selected:
        st.info("Pick at least one run.")
        return

    _render_selected_run_links(runs=selected)

    reports = {run.label: run.report for run in selected}
    timelines = {
        run.label: load_run_timeline(run_dir=run.run_dir, scenario_name=run.scenario_name)
        for run in selected
    }

    report_list = list(reports.values())
    flag_metrics = collect_flag_metrics(reports=report_list)
    value_metrics = collect_value_metrics(reports=report_list)

    if not flag_metrics and not value_metrics:
        st.info("None of the selected runs have metrics with per-round observations.")
        return

    if flag_metrics:
        st.markdown("### Flagged rounds")
        st.caption("Lanes for binary fire/no-fire metrics. One dot per round the metric flagged.")
        chosen_flags = _render_metric_checkboxes(available=flag_metrics)
        if chosen_flags:
            fig = build_timeline_figure(
                reports=reports,
                timelines=timelines,
                metrics=chosen_flags,
            )
            selection_state = st.plotly_chart(
                fig,
                width="stretch",
                on_select="rerun",
                selection_mode=("points",),
                key=_timeline_chart_key(),
            )
            _maybe_open_point_modal(selection_state=selection_state, reports=reports)
        else:
            st.caption("Select at least one flag metric to plot.")

    if value_metrics:
        st.markdown("### Per-round values")
        st.caption(
            "Continuous metrics (perplexity, mcr, mcm, ...) share one Y axis — "
            "colour = run, line style = metric. `round_success*` metrics render "
            "as a rug strip below, one tick per succeeded round."
        )
        chosen_values = _render_value_metric_checkboxes(available=value_metrics)
        if chosen_values:
            value_fig = build_value_metrics_figure(reports=reports, metrics=chosen_values)
            st.plotly_chart(value_fig, width="stretch", key="timeline_value_chart")
        else:
            st.caption("Select at least one value metric to plot.")

    with st.expander("Selected runs — scenario config", expanded=False):
        for run in selected:
            st.markdown(f"**{run.label}**")
            st.json(timelines[run.label].scenario_config)
