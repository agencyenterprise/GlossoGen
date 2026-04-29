"""Streamlit tab plotting resume runs against their source runs.

A radio at the top picks which view is shown:

* **per-round success** — X = simulation round number, Y = success rate over
  that round. One solid line per (replacement_model, round_start) bucket
  (mean across replicas) and one dashed line per source run.
* **window accuracy** — X = round_start, Y = mean fraction of post-swap rounds
  stabilized. One solid line per replacement model and a matched dashed line
  for what the source achieved over the same window.

Both views share the bucket/source filters above the chart. Only runs labeled
``resume`` are eligible.
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

_VIEW_PER_ROUND = "per-round success"
_VIEW_WINDOW = "window accuracy"
_VIEW_OPTIONS = (_VIEW_PER_ROUND, _VIEW_WINDOW)


def _render_view_selector() -> str:
    """Radio letting the user pick which chart is shown."""
    chosen = st.radio(
        label="View",
        options=_VIEW_OPTIONS,
        index=0,
        horizontal=True,
        key="resume_view_selector",
    )
    if isinstance(chosen, str):
        return chosen
    return _VIEW_PER_ROUND


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


def _source_filter(runs: list[ResumeRun]) -> set[str]:
    """One checkbox per distinct source run id; returns selected ids."""
    sources = sorted({run.source_run_id for run in runs})
    if not sources:
        return set()
    st.markdown("**Source runs**")
    selected: set[str] = set()
    for source_run_id in sources:
        count = sum(1 for r in runs if r.source_run_id == source_run_id)
        if st.checkbox(
            label=f"{source_run_id} ({count} resume replicas)",
            value=True,
            key=f"resume_source_filter::{source_run_id}",
        ):
            selected.add(source_run_id)
    return selected


def _resume_bucket_stats(runs: list[ResumeRun]) -> list[SeriesStats]:
    """Aggregate resume runs by (bucket, round_number) into mean-success stats."""
    buckets: dict[tuple[str, int], list[float]] = {}
    for run in runs:
        series = run.resumed_series_key()
        for round_number, succeeded in run.resumed_round_outcomes.items():
            buckets.setdefault((series, round_number), []).append(1.0 if succeeded else 0.0)
    stats: list[SeriesStats] = []
    for (series, round_number), values in sorted(buckets.items()):
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = float(variance**0.5)
        stats.append(
            SeriesStats(
                series=series,
                x_value=float(round_number),
                n=len(values),
                mean=mean,
                std=std,
                min_value=min(values),
                max_value=max(values),
            )
        )
    return stats


def _source_stats(runs: list[ResumeRun]) -> list[SeriesStats]:
    """One ``SeriesStats`` per (source, round) — source is deterministic so std=0.

    Restricted to rounds at or after the earliest ``round_start`` among the
    resume runs that point at that source, so the source line doesn't extend
    into rounds played before any resume began.
    """
    earliest_start_by_source: dict[str, int] = {}
    for run in runs:
        current = earliest_start_by_source.get(run.source_run_id)
        if current is None or run.round_start < current:
            earliest_start_by_source[run.source_run_id] = run.round_start
    seen: dict[tuple[str, int], bool] = {}
    for run in runs:
        threshold = earliest_start_by_source[run.source_run_id]
        for round_number, succeeded in run.source_round_outcomes.items():
            if round_number < threshold:
                continue
            key = (run.source_series_key(), round_number)
            if key not in seen:
                seen[key] = succeeded
    stats: list[SeriesStats] = []
    for (series, round_number), succeeded in sorted(seen.items()):
        value = 1.0 if succeeded else 0.0
        stats.append(
            SeriesStats(
                series=series,
                x_value=float(round_number),
                n=1,
                mean=value,
                std=0.0,
                min_value=value,
                max_value=value,
            )
        )
    return stats


def _replica_dots(runs: list[ResumeRun]) -> dict[str, tuple[list[float], list[float], list[str]]]:
    """Per resume-bucket replica dots: jittered (round, 0/1) for every replica × round."""
    dots: dict[str, tuple[list[float], list[float], list[str]]] = {}
    counter: dict[str, int] = {}
    for run in runs:
        series = run.resumed_series_key()
        bucket = dots.setdefault(series, ([], [], []))
        for round_number, succeeded in sorted(run.resumed_round_outcomes.items()):
            index = counter.get(series, 0)
            bucket[0].append(jittered_x_linear(base_x=float(round_number), index=index))
            bucket[1].append(1.0 if succeeded else 0.0)
            bucket[2].append(
                f"{run.run_id}<br>{series}<br>round={round_number}<br>"
                f"success={'yes' if succeeded else 'no'}"
            )
            counter[series] = index + 1
    return dots


def _build_figure(
    bucket_stats: list[SeriesStats],
    source_stats: list[SeriesStats],
    replica_dots: dict[str, tuple[list[float], list[float], list[str]]],
    x_tickvals: list[int],
) -> go.Figure:
    """Assemble the round → success-rate figure with bucket means and source lines."""
    fig = go.Figure()
    bucket_series = sorted({s.series for s in bucket_stats})
    source_series = sorted({s.series for s in source_stats})
    palette = series_color_map(series_keys=bucket_series + source_series)
    colour_by_bucket = {series: palette[series] for series in bucket_series}
    colour_by_source = {series: palette[series] for series in source_series}
    bucket_stats_by_series: dict[str, list[SeriesStats]] = {}
    for stat in bucket_stats:
        bucket_stats_by_series.setdefault(stat.series, []).append(stat)
    for series, colour in colour_by_bucket.items():
        xs, ys, hover = replica_dots.get(series, ([], [], []))
        if xs:
            add_replica_trace(
                fig=fig, series=series, xs=xs, ys=ys, hover_texts=hover, colour=colour
            )
        add_mean_trace(
            fig=fig,
            series=series,
            stats=bucket_stats_by_series[series],
            metric_display_name="success rate",
            colour=colour,
            dash="solid",
        )
    source_stats_by_series: dict[str, list[SeriesStats]] = {}
    for stat in source_stats:
        source_stats_by_series.setdefault(stat.series, []).append(stat)
    for series, colour in colour_by_source.items():
        add_mean_trace(
            fig=fig,
            series=series,
            stats=source_stats_by_series[series],
            metric_display_name="success",
            colour=colour,
            dash="dash",
        )
    fig.update_layout(
        xaxis=dict(
            title="round number",
            tickmode="array",
            tickvals=x_tickvals,
            ticktext=[str(r) for r in x_tickvals],
        ),
        yaxis=dict(title="success rate (mean across replicas)", range=[-0.05, 1.05], dtick=0.25),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=20, t=40, b=60),
        height=520,
    )
    return fig


def _render_stats_table(bucket_stats: list[SeriesStats], source_stats: list[SeriesStats]) -> None:
    """Tabular view of per-(series, round) means below the chart."""
    rows = [
        {
            "series": s.series,
            "round": int(s.x_value),
            "n": s.n,
            "success rate": round(s.mean, 4),
            "std": round(s.std, 4),
        }
        for s in sorted(bucket_stats + source_stats, key=lambda s: (s.series, s.x_value))
    ]
    st.markdown("### Aggregate statistics")
    st.dataframe(rows, width="stretch", hide_index=True)


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
        resumed_key = (f"{run.replacement_model} · resumed", run.round_start)
        buckets.setdefault(resumed_key, []).append(_resumed_window_accuracy(run=run))
        source_value = _source_window_accuracy(run=run)
        if source_value is None:
            continue
        source_key = (f"{run.replacement_model} · source", run.round_start)
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
            (f"{run.replacement_model} · resumed", _resumed_window_accuracy(run=run)),
            (f"{run.replacement_model} · source", _source_window_accuracy(run=run)),
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
                fig=fig, series=series, xs=xs, ys=ys, hover_texts=hover, colour=colour
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


def _render_per_round_view(
    filtered: list[ResumeRun],
    selected_sources: set[str],
) -> None:
    """Render the per-round success-rate chart + stats table."""
    bucket_stats = _resume_bucket_stats(runs=filtered)
    source_runs_for_lines = [r for r in filtered if r.source_run_id in selected_sources]
    source_stats = _source_stats(runs=source_runs_for_lines)
    replica_dots = _replica_dots(runs=filtered)
    rounds_seen: set[int] = set()
    for stat in bucket_stats:
        rounds_seen.add(int(stat.x_value))
    for stat in source_stats:
        rounds_seen.add(int(stat.x_value))
    x_tickvals = sorted(rounds_seen)
    fig = _build_figure(
        bucket_stats=bucket_stats,
        source_stats=source_stats,
        replica_dots=replica_dots,
        x_tickvals=x_tickvals,
    )
    st.plotly_chart(fig, width="stretch", key="resume_round_success_chart")
    _render_stats_table(bucket_stats=bucket_stats, source_stats=source_stats)


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
    view = _render_view_selector()
    selected_buckets = _bucket_filter(runs=all_resume)
    if not selected_buckets:
        st.info("Select at least one resume bucket.")
        return
    selected_sources = _source_filter(runs=all_resume)
    filtered = [r for r in all_resume if r.resumed_series_key() in selected_buckets]
    if not filtered:
        st.info("No resume runs match the selected buckets.")
        return
    if view == _VIEW_WINDOW:
        _render_window_view(runs=filtered)
    else:
        _render_per_round_view(filtered=filtered, selected_sources=selected_sources)
    _render_included_runs(runs=filtered)
