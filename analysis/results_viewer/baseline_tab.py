"""Streamlit tab rendering the baseline sweep: budget vs a user-chosen metric per series.

A series is one (model, postmortem_enabled) variant — each gets its own line and
colour, so e.g. sonnet-4.6 with postmortem and sonnet-4.6 without postmortem
render as two distinct traces. The user picks which metric is on the Y axis
(``round_success`` / ``round_ended_idle`` / ``round_ended_timeout`` /
``postmortem_ended_timeout`` / ``content_filter_refusal`` / ``perplexity`` /
``mcr`` / ``mcm``); the same chart adapts its Y range
and tick spacing to the selected metric. Clicking a replica dot opens the
corresponding run in the glossogen frontend (URL is attached to each point as
``customdata`` and read back from the chart's selection event).
"""

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer import seed_mode_filter
from analysis.results_viewer.baseline_data import (
    METRIC_OPTIONS,
    BaselineRun,
    BudgetStats,
    MetricOption,
    YAxisSpec,
    aggregate_by_budget,
    list_baseline_runs,
)
from analysis.results_viewer.measurement_scores import read_labels
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import maybe_open_clicked_run, render_frontend_base, run_url
from analysis.results_viewer.scenario_selector import render_scenario_radio
from analysis.results_viewer.series_plot import (
    SeriesStats,
    add_mean_trace,
    add_replica_trace,
    jittered_x,
    render_horizontal_checkboxes,
    series_color_map,
)

_BASELINE_FAMILY_LABELS = frozenset({"baseline", "baseline_oss", "channel_noise"})


def _scenarios_with_baseline_runs(evaluated: list[EvaluatedRun]) -> list[str]:
    """Return every scenario that has at least one baseline-family run.

    Auto-discovered from the loaded runs so any scenario whose runs ship a
    ``baseline``, ``baseline_oss``, or ``channel_noise`` label appears in the
    radio selector without code changes.
    """
    out: set[str] = set()
    for run in evaluated:
        if _BASELINE_FAMILY_LABELS.intersection(read_labels(run_dir=run.run_dir)):
            out.add(run.scenario_name)
    return sorted(out)


def _render_scenario_selector(evaluated: list[EvaluatedRun]) -> str | None:
    """Radio selector listing every scenario that has baseline-labeled runs."""
    options = _scenarios_with_baseline_runs(evaluated=evaluated)
    return render_scenario_radio(options=options, key="baseline_scenario_selector")


def _render_metric_selector() -> MetricOption:
    """Radio selector + info popover letting the user pick the Y-axis metric.

    Renders the radio and a small ``ⓘ`` popover side-by-side; the popover's
    contents describe how the currently selected metric is computed.
    """
    radio_col, info_col = st.columns([8, 1])
    with radio_col:
        display_names = [opt.display_name for opt in METRIC_OPTIONS]
        chosen = st.radio(
            label="Metric",
            options=display_names,
            index=0,
            horizontal=True,
            key="baseline_metric_selector",
        )
    selected = METRIC_OPTIONS[0]
    for option in METRIC_OPTIONS:
        if option.display_name == chosen:
            selected = option
            break
    with info_col:
        st.markdown("&nbsp;")
        with st.popover("ⓘ", help="How this metric is computed"):
            st.markdown(selected.description)
    return selected


def _render_model_filter(runs: list[BaselineRun]) -> set[str]:
    """Checkboxes for each distinct model in the data."""
    counts: dict[str, int] = {}
    for run in runs:
        counts[run.model] = counts.get(run.model, 0) + 1
    options = [(model, model, counts[model]) for model in sorted(counts)]
    return render_horizontal_checkboxes(
        title="Model",
        options=options,
        key_prefix="baseline_model_filter",
        initial_state=True,
    )


def _render_postmortem_filter(runs: list[BaselineRun]) -> set[bool]:
    """Two checkboxes: with-postmortem / without-postmortem."""
    counts = {True: 0, False: 0}
    for run in runs:
        counts[run.postmortem_enabled] += 1
    options = [
        ("postmortem", "with postmortem", counts[True]),
        ("no_postmortem", "no postmortem", counts[False]),
    ]
    options = [(k, lbl, c) for k, lbl, c in options if c > 0]
    selected_keys = render_horizontal_checkboxes(
        title="Postmortem",
        options=options,
        key_prefix="baseline_postmortem_filter",
        initial_state=True,
    )
    selected: set[bool] = set()
    if "postmortem" in selected_keys:
        selected.add(True)
    if "no_postmortem" in selected_keys:
        selected.add(False)
    return selected


def _render_kind_filter(runs: list[BaselineRun]) -> set[str]:
    """One checkbox per run kind present (``baseline``, ``baseline_oss``, and
    per-noise-level ``channel_noise(noise=...)`` variants)."""
    counts: dict[str, int] = {}
    for run in runs:
        counts[run.kind] = counts.get(run.kind, 0) + 1
    options = [(k, k, counts[k]) for k in sorted(counts)]
    return render_horizontal_checkboxes(
        title="Run kind",
        options=options,
        key_prefix="baseline_kind_filter",
        initial_state=True,
    )


def _replica_xs_ys_hover(
    runs: list[BaselineRun],
    series: str,
    metric: MetricOption,
    frontend_base: str,
) -> tuple[list[float], list[float], list[str], list[str]]:
    """Compute jittered X, Y, hover text, and per-point URLs for ``add_replica_trace``.

    The URL is also stamped into the hover and into ``customdata`` so the
    ``render`` function can read it back from the Streamlit selection event
    and open the run in a new tab when the user clicks a dot.
    """
    xs: list[float] = []
    ys: list[float] = []
    hover: list[str] = []
    urls: list[str] = []
    for index, run in enumerate(runs):
        value = metric.extract(run=run)
        url = run_url(frontend_base=frontend_base, run_id=run.run_id)
        xs.append(jittered_x(base_x=run.budget, index=index))
        ys.append(value)
        hover.append(
            f"{run.run_id}<br>{series}<br>budget={run.budget}<br>"
            f"{metric.display_name}={value:g}<br>"
            f"click to open · {url}"
        )
        urls.append(url)
    return xs, ys, hover, urls


def _budget_stats_to_series_stats(stats: list[BudgetStats]) -> list[SeriesStats]:
    """Convert ``BudgetStats`` rows into the shared ``SeriesStats`` shape."""
    return [
        SeriesStats(
            series=s.series,
            x_value=float(s.budget),
            n=s.n,
            mean=s.mean,
            std=s.std,
            min_value=s.min_value,
            max_value=s.max_value,
        )
        for s in stats
    ]


def _build_figure(
    runs: list[BaselineRun],
    stats: list[BudgetStats],
    colour_by_series: dict[str, str],
    metric: MetricOption,
    y_axis: YAxisSpec,
    x_tickvals: list[int],
    frontend_base: str,
) -> go.Figure:
    """Assemble the budget → metric figure with mean ± std and replica dots.

    ``y_axis`` and ``x_tickvals`` are passed in so the axes stay fixed when
    the user toggles series/batch filters; recomputing them from ``runs``
    would shrink the chart whenever a series is hidden.
    """
    fig = go.Figure()
    runs_by_series: dict[str, list[BaselineRun]] = {}
    for run in runs:
        runs_by_series.setdefault(run.series_key(), []).append(run)
    stats_by_series: dict[str, list[BudgetStats]] = {}
    for stat in stats:
        stats_by_series.setdefault(stat.series, []).append(stat)
    # Means are drawn first so the replica scatter sits on top and click events
    # land on replica points (which carry the per-run customdata URL) rather
    # than the larger opaque mean markers.
    for series, colour in colour_by_series.items():
        if series not in runs_by_series:
            continue
        if series in stats_by_series:
            add_mean_trace(
                fig=fig,
                series=series,
                stats=_budget_stats_to_series_stats(stats=stats_by_series[series]),
                metric_display_name=metric.display_name,
                colour=colour,
                dash="solid",
            )
    for series, colour in colour_by_series.items():
        if series not in runs_by_series:
            continue
        xs, ys, hover, urls = _replica_xs_ys_hover(
            runs=runs_by_series[series],
            series=series,
            metric=metric,
            frontend_base=frontend_base,
        )
        add_replica_trace(
            fig=fig,
            series=series,
            xs=xs,
            ys=ys,
            hover_texts=hover,
            colour=colour,
            customdata=urls,
        )
    yaxis_kwargs: dict[str, object] = {
        "title": f"{metric.y_axis_label} (mean ± std)",
        "range": [y_axis.y_min, y_axis.y_max],
    }
    if y_axis.dtick is not None:
        yaxis_kwargs["dtick"] = y_axis.dtick
    fig.update_layout(
        xaxis=dict(
            title="round_time_budget_seconds (log scale)",
            type="log",
            tickmode="array",
            tickvals=x_tickvals,
            ticktext=[str(b) for b in x_tickvals],
        ),
        yaxis=yaxis_kwargs,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=20, t=40, b=60),
        height=500,
    )
    return fig


def _render_stats_table(stats: list[BudgetStats], metric: MetricOption) -> None:
    """Tabular view of the per-bucket statistics below the chart."""
    rows = [
        {
            "series": s.series,
            "budget": s.budget,
            "n": s.n,
            f"{metric.display_name} mean": round(s.mean, 4),
            f"{metric.display_name} std": round(s.std, 4),
            "min": round(s.min_value, 4),
            "max": round(s.max_value, 4),
        }
        for s in sorted(stats, key=lambda s: (s.series, s.budget))
    ]
    st.markdown("### Aggregate statistics")
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_included_runs(
    runs: list[BaselineRun],
    metric: MetricOption,
    frontend_base: str,
) -> None:
    """Per-replica audit listing inside an expander.

    The ``url`` column is rendered as a clickable LinkColumn so users can
    open a specific replica in the glossogen frontend to investigate a high or
    low ``perplexity`` (or any other metric) outlier.
    """
    rows = [
        {
            "series": r.series_key(),
            "budget": r.budget,
            metric.display_name: round(metric.extract(run=r), 4),
            "run_id": r.run_id,
            "url": run_url(frontend_base=frontend_base, run_id=r.run_id),
        }
        for r in sorted(
            runs,
            key=lambda r: (
                r.series_key(),
                r.budget,
                r.run_id,
            ),
        )
    ]
    with st.expander(f"Included runs ({len(rows)})", expanded=False):
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
            column_config={
                "url": st.column_config.LinkColumn(
                    label="open",
                    display_text="↗",
                    help="Open this replica in the glossogen frontend",
                ),
            },
        )


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Baseline tab body."""
    run_filter = seed_mode_filter.render_filters(key_prefix="baseline")
    evaluated = seed_mode_filter.apply(evaluated=evaluated, run_filter=run_filter)
    scenario_name = _render_scenario_selector(evaluated=evaluated)
    if scenario_name is None:
        st.info(
            "No runs labeled 'baseline' found. Add the 'baseline' label and "
            "ensure the scenario_config carries `round_time_budget_seconds`."
        )
        return
    all_baseline = list_baseline_runs(evaluated_runs=evaluated, scenario_name=scenario_name)
    if not all_baseline:
        st.info(
            f"No runs in scenario `{scenario_name}` labeled 'baseline' found. "
            "Add the 'baseline' label and ensure the scenario_config carries "
            "`round_time_budget_seconds`."
        )
        return
    metric = _render_metric_selector()
    frontend_base = render_frontend_base(streamlit_key="baseline_frontend_base")
    selected_models = _render_model_filter(runs=all_baseline)
    selected_postmortem = _render_postmortem_filter(runs=all_baseline)
    selected_kinds = _render_kind_filter(runs=all_baseline)
    if not selected_models:
        st.info("Select at least one model.")
        return
    if not selected_postmortem:
        st.info("Select at least one postmortem option.")
        return
    if not selected_kinds:
        st.info("Select at least one run kind.")
        return
    primary_filtered = [
        run
        for run in all_baseline
        if run.model in selected_models
        and run.postmortem_enabled in selected_postmortem
        and run.kind in selected_kinds
    ]
    if not primary_filtered:
        st.info("No baseline runs for the selected filters.")
        return
    metric_runs = [run for run in primary_filtered if metric.available(run=run)]
    if not metric_runs:
        st.info(
            f"No selected baseline runs have a value for `{metric.display_name}`. "
            "For perplexity, run `python -m glossogen evaluate <scenario> "
            "--metrics perplexity ...` on the runs you want included."
        )
        return
    series_ordered = sorted({r.series_key() for r in metric_runs})
    colour_by_series = series_color_map(series_keys=series_ordered)
    stats = aggregate_by_budget(
        runs=metric_runs,
        value_of=metric.extract,
    )
    # Compute axis ranges from the unfiltered baseline set so the chart's
    # X tick layout and Y range stay constant when the user toggles series.
    y_axis = metric.y_axis(runs=all_baseline)
    x_tickvals = sorted({r.budget for r in all_baseline})
    fig = _build_figure(
        runs=metric_runs,
        stats=stats,
        colour_by_series=colour_by_series,
        metric=metric,
        y_axis=y_axis,
        x_tickvals=x_tickvals,
        frontend_base=frontend_base,
    )
    chart_event = st.plotly_chart(
        fig,
        width="stretch",
        key="baseline_chart",
        on_select="rerun",
        selection_mode=("points",),
    )
    maybe_open_clicked_run(chart_event=chart_event, session_key="baseline_last_opened_url")
    _render_stats_table(stats=stats, metric=metric)
    _render_included_runs(
        runs=metric_runs,
        metric=metric,
        frontend_base=frontend_base,
    )
