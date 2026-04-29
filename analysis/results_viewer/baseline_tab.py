"""Streamlit tab rendering the baseline sweep: budget vs a user-chosen metric per series.

A series is one (model, postmortem_enabled) variant — each gets its own line and
colour, so e.g. sonnet-4.6 with postmortem and sonnet-4.6 without postmortem
render as two distinct traces. The user picks which round-level metric is on
the Y axis (``round_success`` / ``round_ended_idle`` / ``round_ended_timeout``).
"""

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.baseline_data import (
    METRIC_OPTIONS,
    REFUSAL_METRIC,
    BaselineRun,
    BudgetStats,
    MetricOption,
    aggregate_by_budget,
    list_baseline_runs,
)
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.series_plot import (
    SeriesStats,
    add_mean_trace,
    add_replica_trace,
    batch_label_filter,
    jittered_x,
    series_color_map,
)


def _render_metric_selector() -> MetricOption:
    """Radio selector letting the user pick which metric is on the Y axis."""
    display_names = [opt.display_name for opt in METRIC_OPTIONS]
    chosen = st.radio(
        label="Metric",
        options=display_names,
        index=0,
        horizontal=True,
        key="baseline_metric_selector",
    )
    for option in METRIC_OPTIONS:
        if option.display_name == chosen:
            return option
    return METRIC_OPTIONS[0]


def _series_checkbox_filter(
    runs: list[BaselineRun], selected_batch_labels: frozenset[str]
) -> set[str]:
    """Render one checkbox per distinct series; return the set of selected series keys."""
    counts: dict[str, int] = {}
    for run in runs:
        key = run.series_key(selected_batch_labels=selected_batch_labels)
        counts[key] = counts.get(key, 0) + 1
    st.markdown("**Series (model · postmortem variant)**")
    selected: set[str] = set()
    for name in sorted(counts):
        if st.checkbox(
            label=f"{name} ({counts[name]})",
            value=True,
            key=f"baseline_series_filter::{name}",
        ):
            selected.add(name)
    return selected


def _replica_xs_ys_hover(
    runs: list[BaselineRun],
    series: str,
    metric: MetricOption,
) -> tuple[list[float], list[float], list[str]]:
    """Compute jittered X, Y, and hover text per replica for ``add_replica_trace``."""
    xs: list[float] = []
    ys: list[float] = []
    hover: list[str] = []
    for index, run in enumerate(runs):
        value = metric.extract(run=run)
        xs.append(jittered_x(base_x=run.budget, index=index))
        ys.append(value)
        hover.append(
            f"{run.run_id}<br>{series}<br>budget={run.budget}<br>"
            f"{metric.display_name}={value:g}"
        )
    return xs, ys, hover


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
    selected_batch_labels: frozenset[str],
    y_max: float,
    x_tickvals: list[int],
) -> go.Figure:
    """Assemble the budget → metric figure with mean ± std and replica dots.

    ``y_max`` and ``x_tickvals`` are passed in so the axes stay fixed when
    the user toggles series/batch filters; recomputing them from ``runs``
    would shrink the chart whenever a series is hidden.
    """
    fig = go.Figure()
    runs_by_series: dict[str, list[BaselineRun]] = {}
    for run in runs:
        runs_by_series.setdefault(
            run.series_key(selected_batch_labels=selected_batch_labels), []
        ).append(run)
    stats_by_series: dict[str, list[BudgetStats]] = {}
    for stat in stats:
        stats_by_series.setdefault(stat.series, []).append(stat)
    for series, colour in colour_by_series.items():
        xs, ys, hover = _replica_xs_ys_hover(
            runs=runs_by_series[series], series=series, metric=metric
        )
        add_replica_trace(fig=fig, series=series, xs=xs, ys=ys, hover_texts=hover, colour=colour)
        add_mean_trace(
            fig=fig,
            series=series,
            stats=_budget_stats_to_series_stats(stats=stats_by_series[series]),
            metric_display_name=metric.display_name,
            colour=colour,
            dash="solid",
        )
    fig.update_layout(
        xaxis=dict(
            title="round_time_budget_seconds (log scale)",
            type="log",
            tickmode="array",
            tickvals=x_tickvals,
            ticktext=[str(b) for b in x_tickvals],
        ),
        yaxis=dict(
            title=f"{metric.y_axis_label} (mean ± std)",
            range=[0, y_max],
            dtick=1,
        ),
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


def _build_refusal_figure(
    runs: list[BaselineRun],
    stats: list[BudgetStats],
    colour_by_series: dict[str, str],
    selected_batch_labels: frozenset[str],
    y_max: float,
    x_tickvals: list[int],
) -> go.Figure:
    """Dedicated plot for total content-filter refusals per run.

    Separate from the main figure because refusal magnitude (can exceed 100
    per run) doesn't fit the 0..total_rounds Y axis used by the round metrics.
    """
    fig = go.Figure()
    runs_by_series: dict[str, list[BaselineRun]] = {}
    for run in runs:
        runs_by_series.setdefault(
            run.series_key(selected_batch_labels=selected_batch_labels), []
        ).append(run)
    stats_by_series: dict[str, list[BudgetStats]] = {}
    for stat in stats:
        stats_by_series.setdefault(stat.series, []).append(stat)
    for series, colour in colour_by_series.items():
        xs, ys, hover = _replica_xs_ys_hover(
            runs=runs_by_series[series], series=series, metric=REFUSAL_METRIC
        )
        add_replica_trace(fig=fig, series=series, xs=xs, ys=ys, hover_texts=hover, colour=colour)
        add_mean_trace(
            fig=fig,
            series=series,
            stats=_budget_stats_to_series_stats(stats=stats_by_series[series]),
            metric_display_name=REFUSAL_METRIC.display_name,
            colour=colour,
            dash="solid",
        )
    fig.update_layout(
        xaxis=dict(
            title="round_time_budget_seconds (log scale)",
            type="log",
            tickmode="array",
            tickvals=x_tickvals,
            ticktext=[str(b) for b in x_tickvals],
        ),
        yaxis=dict(
            title=f"{REFUSAL_METRIC.y_axis_label} (mean ± std)",
            range=[0, y_max],
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=20, t=40, b=60),
        height=400,
    )
    return fig


def _render_refusal_section(
    runs: list[BaselineRun],
    colour_by_series: dict[str, str],
    selected_batch_labels: frozenset[str],
    refusal_y_max: float,
    x_tickvals: list[int],
) -> None:
    """Render the dedicated Content-filter refusal chart + stats table."""
    st.markdown("---")
    st.markdown("### Content-filter refusals")
    st.caption(
        "Raw count of `ContentFilterError` refusals logged by the agent runner. "
        "The runner retries on refusal, so a single round can accumulate many. "
        "Separate chart because magnitude (dozens to hundreds) doesn't share a Y "
        "axis with the round-count metrics above."
    )
    stats = aggregate_by_budget(
        runs=runs,
        value_of=REFUSAL_METRIC.extract,
        selected_batch_labels=selected_batch_labels,
    )
    fig = _build_refusal_figure(
        runs=runs,
        stats=stats,
        colour_by_series=colour_by_series,
        selected_batch_labels=selected_batch_labels,
        y_max=refusal_y_max,
        x_tickvals=x_tickvals,
    )
    st.plotly_chart(fig, width="stretch", key="baseline_refusal_chart")
    rows = [
        {
            "series": s.series,
            "budget": s.budget,
            "n": s.n,
            "refusals mean": round(s.mean, 2),
            "refusals std": round(s.std, 2),
            "min": int(s.min_value),
            "max": int(s.max_value),
        }
        for s in sorted(stats, key=lambda s: (s.series, s.budget))
    ]
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_included_runs(
    runs: list[BaselineRun],
    metric: MetricOption,
    selected_batch_labels: frozenset[str],
) -> None:
    """Per-replica audit listing inside an expander."""
    rows = [
        {
            "series": r.series_key(selected_batch_labels=selected_batch_labels),
            "budget": r.budget,
            metric.display_name: round(metric.extract(run=r), 4),
            "run_id": r.run_id,
        }
        for r in sorted(
            runs,
            key=lambda r: (
                r.series_key(selected_batch_labels=selected_batch_labels),
                r.budget,
                r.run_id,
            ),
        )
    ]
    with st.expander(f"Included runs ({len(rows)})", expanded=False):
        st.dataframe(rows, width="stretch", hide_index=True)


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Baseline tab body."""
    all_baseline = list_baseline_runs(evaluated_runs=evaluated)
    if not all_baseline:
        st.info(
            "No runs labeled 'baseline' found. "
            "Add the 'baseline' label to runs you want in this view."
        )
        return
    metric = _render_metric_selector()
    excluded = frozenset(run.model for run in all_baseline)
    batch_filtered, selected_batch_labels = batch_label_filter(
        runs=all_baseline,
        labels_of=lambda run: run.labels,
        excluded_label_values=excluded,
        streamlit_key_prefix="baseline_batch_filter",
    )
    if not batch_filtered:
        st.info("Select at least one batch label.")
        return
    selected_series = _series_checkbox_filter(
        runs=batch_filtered, selected_batch_labels=selected_batch_labels
    )
    if not selected_series:
        st.info("Select at least one series.")
        return
    filtered = [
        run
        for run in batch_filtered
        if run.series_key(selected_batch_labels=selected_batch_labels) in selected_series
    ]
    if not filtered:
        st.info("No baseline runs for the selected series.")
        return
    series_ordered = sorted(
        {r.series_key(selected_batch_labels=selected_batch_labels) for r in filtered}
    )
    colour_by_series = series_color_map(series_keys=series_ordered)
    stats = aggregate_by_budget(
        runs=filtered,
        value_of=metric.extract,
        selected_batch_labels=selected_batch_labels,
    )
    # Compute axis ranges from the unfiltered baseline set so the chart's
    # X tick layout and Y range stay constant when the user toggles series.
    y_max = max((run.total_rounds for run in all_baseline), default=15)
    refusal_observed_max = max(
        (REFUSAL_METRIC.extract(run=run) for run in all_baseline),
        default=0.0,
    )
    refusal_y_max = max(refusal_observed_max * 1.1, 10.0)
    x_tickvals = sorted({r.budget for r in all_baseline})
    fig = _build_figure(
        runs=filtered,
        stats=stats,
        colour_by_series=colour_by_series,
        metric=metric,
        selected_batch_labels=selected_batch_labels,
        y_max=y_max,
        x_tickvals=x_tickvals,
    )
    st.plotly_chart(fig, width="stretch", key="baseline_chart")
    _render_stats_table(stats=stats, metric=metric)
    _render_refusal_section(
        runs=filtered,
        colour_by_series=colour_by_series,
        selected_batch_labels=selected_batch_labels,
        refusal_y_max=refusal_y_max,
        x_tickvals=x_tickvals,
    )
    _render_included_runs(runs=filtered, metric=metric, selected_batch_labels=selected_batch_labels)
