"""Streamlit tab plotting cross-run replace-agent runs against sources A and B.

X = round_start, Y = mean fraction of rounds stabilized **from round_start
onward**. The solid line is the swapped run's accuracy over its post-swap
window. The dashed line is source A's accuracy over the same round window
(rounds [round_start, end] in the original sim A); the dotted line is
source B's accuracy over the same window. Source labels carry the model
that actually played the source's replaced agent (e.g. opus for A, gpt-5.4
for B) — not the imported model. Only runs labeled ``cross_team`` are
eligible.
"""

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.cross_swap_data import CrossSwapRun, list_cross_swap_runs
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.series_plot import (
    SeriesStats,
    add_mean_trace,
    add_replica_trace,
    jittered_x_linear,
    series_color_map,
)


def _swapped_series(run: CrossSwapRun) -> str:
    """Series key for the cross-run swapped line (the imported agent's model)."""
    return f"{run.imported_model} · swapped"


def _source_a_series(run: CrossSwapRun) -> str:
    """Series key for source A's matched-window line, labelled with A's actual model."""
    return f"{run.source_a_replaced_agent_model} · source A"


def _source_b_series(run: CrossSwapRun) -> str:
    """Series key for source B's matched-window line, labelled with B's actual model."""
    return f"{run.source_b_replaced_agent_model} · source B"


def _bucket_filter(runs: list[CrossSwapRun]) -> set[str]:
    """One checkbox per distinct (model · round_start) bucket; returns selected keys."""
    counts: dict[str, int] = {}
    for run in runs:
        key = run.swapped_series_key()
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return set()
    st.markdown("**Cross-swap buckets (model · round_start)**")
    selected: set[str] = set()
    for name in sorted(counts):
        if st.checkbox(
            label=f"{name} ({counts[name]} replicas)",
            value=True,
            key=f"cross_swap_bucket_filter::{name}",
        ):
            selected.add(name)
    return selected


def _swapped_window_accuracy(run: CrossSwapRun) -> float:
    """Mean success across the rounds the swapped run actually played."""
    values = list(run.swapped_round_outcomes.values())
    return sum(1.0 for v in values if v) / len(values)


def _from_round_start_accuracy(outcomes: dict[int, bool], round_start: int) -> float | None:
    """Mean success across rounds at or after ``round_start`` in ``outcomes``."""
    sliced = [v for round_number, v in outcomes.items() if round_number >= round_start]
    if not sliced:
        return None
    return sum(1.0 for v in sliced if v) / len(sliced)


def _aggregate_window_stats(runs: list[CrossSwapRun]) -> list[SeriesStats]:
    """Bucket per-replica accuracies by (series, round_start).

    Each cross-swap run contributes the swapped run's post-swap window
    accuracy. Each unique source-A/source-B run contributes its accuracy
    over rounds at or after ``round_start`` once per ``(series, round_start)``
    bucket it shows up in, so repeat-source replicas don't inflate the source
    baselines.
    """
    buckets: dict[tuple[str, int], list[float]] = {}
    seen_source_runs: dict[tuple[str, int], set[str]] = {}
    for run in runs:
        swapped_key = (_swapped_series(run=run), run.round_start)
        buckets.setdefault(swapped_key, []).append(_swapped_window_accuracy(run=run))
        source_a_value = _from_round_start_accuracy(
            outcomes=run.source_a_round_outcomes, round_start=run.round_start
        )
        if source_a_value is not None:
            source_a_key = (_source_a_series(run=run), run.round_start)
            seen = seen_source_runs.setdefault(source_a_key, set())
            if run.source_a_run_id not in seen:
                seen.add(run.source_a_run_id)
                buckets.setdefault(source_a_key, []).append(source_a_value)
        source_b_value = _from_round_start_accuracy(
            outcomes=run.source_b_round_outcomes, round_start=run.round_start
        )
        if source_b_value is not None:
            source_b_key = (_source_b_series(run=run), run.round_start)
            seen = seen_source_runs.setdefault(source_b_key, set())
            if run.source_b_run_id not in seen:
                seen.add(run.source_b_run_id)
                buckets.setdefault(source_b_key, []).append(source_b_value)
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
    runs: list[CrossSwapRun],
) -> dict[str, tuple[list[float], list[float], list[str]]]:
    """Per-series jittered (round_start, accuracy) replica points for the chart.

    Swapped dots are one per replica. Source-A/B dots are one per *unique*
    source run id within each ``(series, round_start)`` bucket, so a source
    that shows up across many replicas is still drawn as a single dot.
    """
    dots: dict[str, tuple[list[float], list[float], list[str]]] = {}
    counter: dict[str, int] = {}
    seen_source_dots: dict[tuple[str, int], set[str]] = {}
    for run in runs:
        swapped_value = _swapped_window_accuracy(run=run)
        bucket = dots.setdefault(_swapped_series(run=run), ([], [], []))
        index = counter.get(_swapped_series(run=run), 0)
        bucket[0].append(jittered_x_linear(base_x=float(run.round_start), index=index))
        bucket[1].append(swapped_value)
        bucket[2].append(
            f"{run.run_id}<br>{_swapped_series(run=run)}<br>"
            f"round_start={run.round_start}<br>accuracy={swapped_value:.3f}"
        )
        counter[_swapped_series(run=run)] = index + 1
        for series_fn, source_run_id, outcomes in (
            (_source_a_series, run.source_a_run_id, run.source_a_round_outcomes),
            (_source_b_series, run.source_b_run_id, run.source_b_round_outcomes),
        ):
            value = _from_round_start_accuracy(outcomes=outcomes, round_start=run.round_start)
            if value is None:
                continue
            series = series_fn(run=run)
            seen = seen_source_dots.setdefault((series, run.round_start), set())
            if source_run_id in seen:
                continue
            seen.add(source_run_id)
            bucket = dots.setdefault(series, ([], [], []))
            index = counter.get(series, 0)
            bucket[0].append(jittered_x_linear(base_x=float(run.round_start), index=index))
            bucket[1].append(value)
            bucket[2].append(
                f"{source_run_id}<br>{series}<br>round_start={run.round_start}<br>"
                f"accuracy from R{run.round_start}={value:.3f}"
            )
            counter[series] = index + 1
    return dots


def _series_dash(series: str) -> str:
    """Dash style by series role: solid swapped, dashed source A, dotted source B."""
    if series.endswith(" · source A"):
        return "dash"
    if series.endswith(" · source B"):
        return "dot"
    return "solid"


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
        add_mean_trace(
            fig=fig,
            series=series,
            stats=stats_by_series[series],
            metric_display_name="window accuracy",
            colour=colour,
            dash=_series_dash(series=series),
        )
    fig.update_layout(
        xaxis=dict(
            title="round_start",
            tickmode="array",
            tickvals=x_tickvals,
            ticktext=[f"R{r}" for r in x_tickvals],
        ),
        yaxis=dict(title="round success (mean ± std)", range=[-0.05, 1.05], dtick=0.25),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=20, t=40, b=60),
        height=420,
    )
    return fig


def _render_window_view(runs: list[CrossSwapRun]) -> None:
    """Render the per-window aggregate accuracy chart + caption."""
    st.caption(
        "Solid: mean success across each swapped replica's post-swap rounds. "
        "Dashed: source A's accuracy over rounds at or after round_start "
        "(matched window in the original sim A). Dotted: source B's accuracy "
        "over the same window. Source-line labels carry the model that "
        "actually played the source run's replaced agent. Each unique source "
        "run is counted once per bucket so repeat-source replicas don't stack "
        "the baseline."
    )
    stats = _aggregate_window_stats(runs=runs)
    if not stats:
        st.info("No window data to plot.")
        return
    replica_dots = _window_replica_dots(runs=runs)
    x_tickvals = sorted({int(s.x_value) for s in stats})
    fig = _build_window_figure(stats=stats, replica_dots=replica_dots, x_tickvals=x_tickvals)
    st.plotly_chart(fig, width="stretch", key="cross_swap_window_accuracy_chart")


def _render_included_runs(runs: list[CrossSwapRun]) -> None:
    """Per-replica audit listing inside an expander."""
    rows = [
        {
            "series": run.swapped_series_key(),
            "round_start": run.round_start,
            "rounds_after_swap": run.rounds_after_swap,
            "source_b_round_end": run.source_b_round_end,
            "imported_model": run.imported_model,
            "rounds_played": len(run.swapped_round_outcomes),
            "rounds_won": sum(1 for ok in run.swapped_round_outcomes.values() if ok),
            "source_a_run_id": run.source_a_run_id,
            "source_b_run_id": run.source_b_run_id,
            "run_id": run.run_id,
        }
        for run in sorted(runs, key=lambda r: (r.swapped_series_key(), r.run_id))
    ]
    with st.expander(f"Included runs ({len(rows)})", expanded=False):
        st.dataframe(rows, width="stretch", hide_index=True)


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Cross-swap tab body."""
    all_cross_swap = list_cross_swap_runs(evaluated_runs=evaluated)
    if not all_cross_swap:
        st.info(
            "No runs labeled 'cross_team' found. "
            "Add the 'cross_team' label to cross-run replace-agent runs you want compared here."
        )
        return
    selected_buckets = _bucket_filter(runs=all_cross_swap)
    if not selected_buckets:
        st.info("Select at least one cross-swap bucket.")
        return
    filtered = [r for r in all_cross_swap if r.swapped_series_key() in selected_buckets]
    if not filtered:
        st.info("No cross-swap runs match the selected buckets.")
        return
    _render_window_view(runs=filtered)
    _render_included_runs(runs=filtered)
