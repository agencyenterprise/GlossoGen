"""Streamlit tab plotting resume runs against their source runs.

X = round_start, Y = mean fraction of post-swap rounds stabilized. One solid
line per replacement model and a matched dashed line for what the source
achieved over the same window. Only runs labeled ``resume`` are eligible.
"""

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.resume_data import ResumeRun, list_resume_runs
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.series_plot import (
    SeriesStats,
    add_mean_trace,
    add_replica_trace,
    jittered_x_linear,
    series_color_map,
)


def _window_resumed_series(run: ResumeRun) -> str:
    """Window-view series key for the resumed line, split by bugfix tag."""
    suffix = " · bugfix" if run.has_bugfix() else ""
    return f"{run.replacement_model}{suffix} · resumed"


def _window_source_series(run: ResumeRun) -> str:
    """Window-view series key for the matched source line, split by bugfix tag."""
    suffix = " · bugfix" if run.has_bugfix() else ""
    return f"{run.replacement_model}{suffix} · source"


def _bucket_filter(runs: list[ResumeRun]) -> set[str]:
    """One checkbox per distinct resume-bucket key; returns selected keys."""
    counts: dict[str, int] = {}
    for run in runs:
        key = run.resumed_series_key()
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return set()
    st.markdown("**Resume buckets (model · round_start)**")
    selected: set[str] = set()
    for name in sorted(counts):
        if st.checkbox(
            label=f"{name} ({counts[name]} replicas)",
            value=True,
            key=f"resume_bucket_filter::{name}",
        ):
            selected.add(name)
    return selected


def _resumed_window_accuracy(run: ResumeRun) -> float:
    """Mean success across the rounds the resume actually played."""
    values = list(run.resumed_round_outcomes.values())
    return sum(1.0 for v in values if v) / len(values)


def _source_window_accuracy(run: ResumeRun) -> float | None:
    """Mean source success over the rounds the resume actually played, if any overlap."""
    matched = [
        run.source_round_outcomes[round_number]
        for round_number in run.resumed_round_outcomes
        if round_number in run.source_round_outcomes
    ]
    if not matched:
        return None
    return sum(1.0 for v in matched if v) / len(matched)


def _aggregate_window_stats(
    runs: list[ResumeRun],
) -> list[SeriesStats]:
    """Bucket per-replica window accuracies by (model · variant, round_start).

    One series per (replacement_model, "resumed"|"source") pair so each model
    contributes a solid resumed line and a dashed source line.
    """
    buckets: dict[tuple[str, int], list[float]] = {}
    for run in runs:
        resumed_key = (_window_resumed_series(run=run), run.round_start)
        buckets.setdefault(resumed_key, []).append(_resumed_window_accuracy(run=run))
        source_value = _source_window_accuracy(run=run)
        if source_value is None:
            continue
        source_key = (_window_source_series(run=run), run.round_start)
        buckets.setdefault(source_key, []).append(source_value)
    stats: list[SeriesStats] = []
    for (series, round_start), values in sorted(buckets.items()):
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = float(variance**0.5)
        stats.append(
            SeriesStats(
                series=series,
                x_value=float(round_start),
                n=len(values),
                mean=mean,
                std=std,
                min_value=min(values),
                max_value=max(values),
            )
        )
    return stats


def _window_replica_dots(
    runs: list[ResumeRun],
) -> dict[str, tuple[list[float], list[float], list[str]]]:
    """Per-series jittered (round_start, accuracy) replica points for the window chart."""
    dots: dict[str, tuple[list[float], list[float], list[str]]] = {}
    counter: dict[str, int] = {}
    for run in runs:
        for series, value in (
            (_window_resumed_series(run=run), _resumed_window_accuracy(run=run)),
            (_window_source_series(run=run), _source_window_accuracy(run=run)),
        ):
            if value is None:
                continue
            bucket = dots.setdefault(series, ([], [], []))
            index = counter.get(series, 0)
            bucket[0].append(jittered_x_linear(base_x=float(run.round_start), index=index))
            bucket[1].append(value)
            bucket[2].append(
                f"{run.run_id}<br>{series}<br>round_start={run.round_start}<br>"
                f"accuracy={value:.3f}"
            )
            counter[series] = index + 1
    return dots


def _build_window_figure(
    stats: list[SeriesStats],
    replica_dots: dict[str, tuple[list[float], list[float], list[str]]],
    x_tickvals: list[int],
) -> go.Figure:
    """Per-window-accuracy figure: X = round_start, Y = mean fraction stabilized."""
    fig = go.Figure()
    series_keys = sorted({s.series for s in stats})
    palette = series_color_map(series_keys=series_keys)
    stats_by_series: dict[str, list[SeriesStats]] = {}
    for stat in stats:
        stats_by_series.setdefault(stat.series, []).append(stat)
    for series, colour in palette.items():
        xs, ys, hover = replica_dots.get(series, ([], [], []))
        if xs:
            add_replica_trace(
                fig=fig,
                series=series,
                xs=xs,
                ys=ys,
                hover_texts=hover,
                colour=colour,
                customdata=None,
            )
        dash = "dash" if series.endswith(" · source") else "solid"
        add_mean_trace(
            fig=fig,
            series=series,
            stats=stats_by_series[series],
            metric_display_name="window accuracy",
            colour=colour,
            dash=dash,
        )
    fig.update_layout(
        xaxis=dict(
            title="round_start",
            tickmode="array",
            tickvals=x_tickvals,
            ticktext=[f"R{r}" for r in x_tickvals],
        ),
        yaxis=dict(title="post-swap window accuracy (mean ± std)", range=[-0.05, 1.05], dtick=0.25),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=20, t=40, b=60),
        height=420,
    )
    return fig


def _render_window_view(runs: list[ResumeRun]) -> None:
    """Render the per-window aggregate accuracy chart + caption."""
    st.caption(
        "Per replica, mean success across the rounds it actually played; "
        "the dashed line is what the source achieved over the same rounds."
    )
    stats = _aggregate_window_stats(runs=runs)
    if not stats:
        st.info("No window data to plot.")
        return
    replica_dots = _window_replica_dots(runs=runs)
    x_tickvals = sorted({int(s.x_value) for s in stats})
    fig = _build_window_figure(stats=stats, replica_dots=replica_dots, x_tickvals=x_tickvals)
    st.plotly_chart(fig, width="stretch", key="resume_window_accuracy_chart")


def _render_included_runs(runs: list[ResumeRun]) -> None:
    """Per-replica audit listing inside an expander."""
    rows = [
        {
            "series": run.resumed_series_key(),
            "round_start": run.round_start,
            "rounds_after_swap": run.rounds_after_swap,
            "model": run.replacement_model,
            "rounds_played": len(run.resumed_round_outcomes),
            "rounds_won": sum(1 for ok in run.resumed_round_outcomes.values() if ok),
            "source_run_id": run.source_run_id,
            "run_id": run.run_id,
        }
        for run in sorted(runs, key=lambda r: (r.resumed_series_key(), r.run_id))
    ]
    with st.expander(f"Included runs ({len(rows)})", expanded=False):
        st.dataframe(rows, width="stretch", hide_index=True)


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Resume tab body."""
    all_resume = list_resume_runs(evaluated_runs=evaluated)
    if not all_resume:
        st.info(
            "No runs labeled 'resume' found. "
            "Add the 'resume' label to replace-agent runs you want compared here."
        )
        return
    selected_buckets = _bucket_filter(runs=all_resume)
    if not selected_buckets:
        st.info("Select at least one resume bucket.")
        return
    filtered = [r for r in all_resume if r.resumed_series_key() in selected_buckets]
    if not filtered:
        st.info("No resume runs match the selected buckets.")
        return
    _render_window_view(runs=filtered)
    _render_included_runs(runs=filtered)
