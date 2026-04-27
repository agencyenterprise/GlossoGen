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
from analysis.results_viewer.timeline_plot import palette_color_for_index


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


def _series_checkbox_filter(runs: list[BaselineRun]) -> set[str]:
    """Render one checkbox per distinct series; return the set of selected series keys."""
    counts: dict[str, int] = {}
    for run in runs:
        counts[run.series_key] = counts.get(run.series_key, 0) + 1
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


_CORE_LABEL_PREFIXES = ("baseline", "budget=", "eval:", "postmortem=", "single_team", "two_team")


def _batch_label_filter(runs: list[BaselineRun]) -> list[BaselineRun]:
    """Render checkboxes for non-core batch labels; return runs matching all selected labels.

    Detects labels that aren't part of the standard baseline metadata (budget,
    eval results, model, postmortem variant, team structure) and surfaces them
    as opt-in checkboxes. Runs that carry none of the detected batch labels are
    always included — they predate sub-batch tagging.
    """
    batch_labels: set[str] = set()
    for run in runs:
        for label in run.labels:
            if not any(label.startswith(prefix) for prefix in _CORE_LABEL_PREFIXES):
                if label not in (run.model,):
                    batch_labels.add(label)
    if not batch_labels:
        return runs
    st.markdown("**Batch labels**")
    selected: set[str] = set()
    for label in sorted(batch_labels):
        count = sum(1 for r in runs if label in r.labels)
        if st.checkbox(
            label=f"{label} ({count})",
            value=True,
            key=f"baseline_batch_filter::{label}",
        ):
            selected.add(label)
    if not selected:
        return []
    return [
        r
        for r in runs
        if any(label in r.labels for label in selected)
        or not any(label in r.labels for label in batch_labels)
    ]


def _series_color_map(series_keys: list[str]) -> dict[str, str]:
    """Assign a palette colour to each series, stable across reruns."""
    return {key: palette_color_for_index(index=i) for i, key in enumerate(series_keys)}


def _add_replica_trace(
    fig: go.Figure,
    series: str,
    runs: list[BaselineRun],
    colour: str,
    metric: MetricOption,
) -> None:
    """Scatter the individual replicas with light X-jitter so overlapping points resolve."""
    xs: list[float] = []
    ys: list[float] = []
    hover: list[str] = []
    for index, run in enumerate(runs):
        jitter = 1.0 + ((index % 5) - 2) * 0.01
        value = metric.extract(run=run)
        xs.append(run.budget * jitter)
        ys.append(value)
        hover.append(
            f"{run.run_id}<br>{series}<br>budget={run.budget}<br>"
            f"{metric.display_name}={value:g}"
        )
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            name=f"{series} · replicas",
            marker=dict(color=colour, size=7, opacity=0.35),
            hovertext=hover,
            hoverinfo="text",
            showlegend=False,
        )
    )


def _add_mean_trace(
    fig: go.Figure,
    series: str,
    stats: list[BudgetStats],
    colour: str,
    metric: MetricOption,
) -> None:
    """Mean line with std error bars for a single series."""
    stats_sorted = sorted(stats, key=lambda s: s.budget)
    fig.add_trace(
        go.Scatter(
            x=[s.budget for s in stats_sorted],
            y=[s.mean for s in stats_sorted],
            error_y=dict(
                type="data",
                array=[s.std for s in stats_sorted],
                visible=True,
                thickness=1.5,
                width=6,
                color=colour,
            ),
            mode="lines+markers",
            name=series,
            line=dict(color=colour, width=2.5),
            marker=dict(color=colour, size=10, symbol="circle"),
            hovertemplate=(
                f"series=%{{text}}<br>budget=%{{x}}<br>{metric.display_name} "
                "mean=%{y:g}<extra></extra>"
            ),
            text=[series] * len(stats_sorted),
        )
    )


def _build_figure(
    runs: list[BaselineRun],
    stats: list[BudgetStats],
    colour_by_series: dict[str, str],
    metric: MetricOption,
) -> go.Figure:
    """Assemble the budget → metric figure with mean ± std and replica dots."""
    fig = go.Figure()
    runs_by_series: dict[str, list[BaselineRun]] = {}
    for run in runs:
        runs_by_series.setdefault(run.series_key, []).append(run)
    stats_by_series: dict[str, list[BudgetStats]] = {}
    for stat in stats:
        stats_by_series.setdefault(stat.series, []).append(stat)
    for series, colour in colour_by_series.items():
        _add_replica_trace(
            fig=fig,
            series=series,
            runs=runs_by_series[series],
            colour=colour,
            metric=metric,
        )
        _add_mean_trace(
            fig=fig,
            series=series,
            stats=stats_by_series[series],
            colour=colour,
            metric=metric,
        )
    budgets_sorted = sorted({s.budget for s in stats})
    y_max = max((run.total_rounds for run in runs), default=15)
    fig.update_layout(
        xaxis=dict(
            title="round_time_budget_seconds (log scale)",
            type="log",
            tickmode="array",
            tickvals=budgets_sorted,
            ticktext=[str(b) for b in budgets_sorted],
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
) -> go.Figure:
    """Dedicated plot for total content-filter refusals per run.

    Separate from the main figure because refusal magnitude (can exceed 100
    per run) doesn't fit the 0..total_rounds Y axis used by the round metrics.
    """
    fig = go.Figure()
    runs_by_series: dict[str, list[BaselineRun]] = {}
    for run in runs:
        runs_by_series.setdefault(run.series_key, []).append(run)
    stats_by_series: dict[str, list[BudgetStats]] = {}
    for stat in stats:
        stats_by_series.setdefault(stat.series, []).append(stat)
    for series, colour in colour_by_series.items():
        _add_replica_trace(
            fig=fig,
            series=series,
            runs=runs_by_series[series],
            colour=colour,
            metric=REFUSAL_METRIC,
        )
        _add_mean_trace(
            fig=fig,
            series=series,
            stats=stats_by_series[series],
            colour=colour,
            metric=REFUSAL_METRIC,
        )
    budgets_sorted = sorted({s.budget for s in stats})
    observed_max = max((REFUSAL_METRIC.extract(run=run) for run in runs), default=0.0)
    y_max = max(observed_max * 1.1, 10.0)
    fig.update_layout(
        xaxis=dict(
            title="round_time_budget_seconds (log scale)",
            type="log",
            tickmode="array",
            tickvals=budgets_sorted,
            ticktext=[str(b) for b in budgets_sorted],
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
    stats = aggregate_by_budget(runs=runs, value_of=REFUSAL_METRIC.extract)
    fig = _build_refusal_figure(runs=runs, stats=stats, colour_by_series=colour_by_series)
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


def _render_included_runs(runs: list[BaselineRun], metric: MetricOption) -> None:
    """Per-replica audit listing inside an expander."""
    rows = [
        {
            "series": r.series_key,
            "budget": r.budget,
            metric.display_name: round(metric.extract(run=r), 4),
            "run_id": r.run_id,
        }
        for r in sorted(runs, key=lambda r: (r.series_key, r.budget, r.run_id))
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
    batch_filtered = _batch_label_filter(runs=all_baseline)
    if not batch_filtered:
        st.info("Select at least one batch label.")
        return
    selected_series = _series_checkbox_filter(runs=batch_filtered)
    if not selected_series:
        st.info("Select at least one series.")
        return
    filtered = [run for run in batch_filtered if run.series_key in selected_series]
    if not filtered:
        st.info("No baseline runs for the selected series.")
        return
    series_ordered = sorted({r.series_key for r in filtered})
    colour_by_series = _series_color_map(series_keys=series_ordered)
    stats = aggregate_by_budget(runs=filtered, value_of=metric.extract)
    fig = _build_figure(
        runs=filtered,
        stats=stats,
        colour_by_series=colour_by_series,
        metric=metric,
    )
    st.plotly_chart(fig, width="stretch", key="baseline_chart")
    _render_stats_table(stats=stats, metric=metric)
    _render_refusal_section(runs=filtered, colour_by_series=colour_by_series)
    _render_included_runs(runs=filtered, metric=metric)
