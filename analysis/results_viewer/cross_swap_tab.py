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

import json
from typing import NamedTuple

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from analysis.results_viewer.cross_swap_data import CrossSwapRun, list_cross_swap_runs
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.series_plot import (
    SeriesStats,
    add_mean_trace,
    add_replica_trace,
    jittered_x_linear,
    series_color_map,
)


def _render_frontend_base() -> str:
    """Text input for the schmidt frontend base URL used to deep-link runs."""
    raw = st.text_input(
        label="Frontend base URL (for run links)",
        value="http://localhost:3000",
        key="cross_swap_frontend_base",
        help=(
            "Click a dot in the chart to open the corresponding swapped or source "
            "run at `<base>/runs/<scenario>/<run_dir_name>`."
        ),
    )
    return raw.rstrip("/")


def _run_url(frontend_base: str, run_id: str) -> str:
    """Build the per-run frontend URL: ``<base>/runs/<scenario>/<run_dir_name>``."""
    return f"{frontend_base}/runs/{run_id}"


def _swapped_series(run: CrossSwapRun) -> str:
    """Series key for the cross-run swapped line (the imported agent's model)."""
    return f"{run.imported_model} · swapped"


def _source_a_series(run: CrossSwapRun) -> str:
    """Series key for source A's matched-window line, labelled with A's actual model."""
    return f"{run.source_a_replaced_agent_model} · source A"


def _source_b_series(run: CrossSwapRun) -> str:
    """Series key for source B's matched-window line, labelled with B's actual model."""
    return f"{run.source_b_replaced_agent_model} · source B"


class _SourcePair(NamedTuple):
    """A unique ``(source_a_run_id, source_b_run_id)`` pair with display models."""

    source_a_run_id: str
    source_b_run_id: str
    source_a_model: str
    source_b_model: str

    def label(self) -> str:
        """Human-readable label used in the selectbox and as the section header."""
        return (
            f"{self.source_a_run_id} [{self.source_a_model}]  →  "
            f"{self.source_b_run_id} [{self.source_b_model}]"
        )


def _distinct_source_pairs(runs: list[CrossSwapRun]) -> list[_SourcePair]:
    """Return sorted-by-label distinct source pairs across ``runs``."""
    seen: dict[tuple[str, str], _SourcePair] = {}
    for run in runs:
        key = (run.source_a_run_id, run.source_b_run_id)
        if key in seen:
            continue
        seen[key] = _SourcePair(
            source_a_run_id=run.source_a_run_id,
            source_b_run_id=run.source_b_run_id,
            source_a_model=run.source_a_replaced_agent_model,
            source_b_model=run.source_b_replaced_agent_model,
        )
    return sorted(seen.values(), key=lambda pair: pair.label())


def _render_source_pair_selector(pairs: list[_SourcePair]) -> _SourcePair:
    """Single-select dropdown over the distinct source pairs in the data."""
    labels = [pair.label() for pair in pairs]
    chosen_label = st.selectbox(
        label="Source pair (Sim A → Sim B)",
        options=labels,
        index=0,
        key="cross_swap_source_pair",
        help=(
            "Each entry is a distinct cross-team experiment. Selecting a pair "
            "limits the chart and table below to runs whose source A and "
            "source B match the chosen pair."
        ),
    )
    for pair in pairs:
        if pair.label() == chosen_label:
            return pair
    return pairs[0]


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


class _ReplicaDots(NamedTuple):
    """Per-series jittered points + per-point URLs for the cross-swap chart."""

    xs: list[float]
    ys: list[float]
    hover_texts: list[str]
    urls: list[str]


def _window_replica_dots(runs: list[CrossSwapRun], frontend_base: str) -> dict[str, _ReplicaDots]:
    """Per-series jittered (round_start, accuracy) replica points for the chart.

    Swapped dots are one per replica. Source-A/B dots are one per *unique*
    source run id within each ``(series, round_start)`` bucket, so a source
    that shows up across many replicas is still drawn as a single dot.
    Each dot carries a frontend URL so the click handler can open the run.
    """
    dots: dict[str, _ReplicaDots] = {}
    counter: dict[str, int] = {}
    seen_source_dots: dict[tuple[str, int], set[str]] = {}
    for run in runs:
        swapped_value = _swapped_window_accuracy(run=run)
        swapped_series = _swapped_series(run=run)
        swapped_url = _run_url(frontend_base=frontend_base, run_id=run.run_id)
        bucket = dots.setdefault(swapped_series, _ReplicaDots([], [], [], []))
        index = counter.get(swapped_series, 0)
        bucket.xs.append(jittered_x_linear(base_x=float(run.round_start), index=index))
        bucket.ys.append(swapped_value)
        bucket.hover_texts.append(
            f"{run.run_id}<br>{swapped_series}<br>"
            f"round_start={run.round_start}<br>accuracy={swapped_value:.3f}<br>"
            f"click to open · {swapped_url}"
        )
        bucket.urls.append(swapped_url)
        counter[swapped_series] = index + 1
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
            url = _run_url(frontend_base=frontend_base, run_id=source_run_id)
            bucket = dots.setdefault(series, _ReplicaDots([], [], [], []))
            index = counter.get(series, 0)
            bucket.xs.append(jittered_x_linear(base_x=float(run.round_start), index=index))
            bucket.ys.append(value)
            bucket.hover_texts.append(
                f"{source_run_id}<br>{series}<br>round_start={run.round_start}<br>"
                f"accuracy from R{run.round_start}={value:.3f}<br>"
                f"click to open · {url}"
            )
            bucket.urls.append(url)
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
    replica_dots: dict[str, _ReplicaDots],
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
        dots = replica_dots.get(series)
        if dots is not None and dots.xs:
            add_replica_trace(
                fig=fig,
                series=series,
                xs=dots.xs,
                ys=dots.ys,
                hover_texts=dots.hover_texts,
                colour=colour,
                customdata=dots.urls,
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


def _maybe_open_clicked_run(chart_event: object) -> None:
    """Open the most recently clicked dot's run in a new browser tab.

    Streamlit reruns the script on every selection change, so we de-duplicate
    via ``st.session_state["cross_swap_last_opened_url"]`` to avoid re-opening
    the same run when the user toggles an unrelated filter. The actual
    navigation is done by injecting a ``window.open`` script via
    ``components.html``.
    """
    selection = getattr(chart_event, "selection", None)
    if selection is None:
        return
    points = selection.get("points") if isinstance(selection, dict) else None
    if not points:
        return
    last_point = points[-1]
    customdata = last_point.get("customdata")
    if not customdata:
        return
    if isinstance(customdata, list):
        url = customdata[0] if customdata else None
    else:
        url = customdata
    if not isinstance(url, str) or not url:
        return
    last_key = "cross_swap_last_opened_url"
    if st.session_state.get(last_key) == url:
        return
    st.session_state[last_key] = url
    encoded = json.dumps(url)
    components.html(
        f"<script>window.open({encoded}, '_blank', 'noopener,noreferrer');</script>",
        height=0,
    )
    st.toast(f"opened {url}", icon="↗")


def _render_window_view(runs: list[CrossSwapRun], frontend_base: str) -> None:
    """Render the per-window aggregate accuracy chart + caption."""
    st.caption(
        "Solid: mean success across each swapped replica's post-swap rounds. "
        "Dashed: source A's accuracy over rounds at or after round_start "
        "(matched window in the original sim A). Dotted: source B's accuracy "
        "over the same window. Source-line labels carry the model that "
        "actually played the source run's replaced agent. Each unique source "
        "run is counted once per bucket so repeat-source replicas don't stack "
        "the baseline. Click any dot to open that run in a new tab."
    )
    stats = _aggregate_window_stats(runs=runs)
    if not stats:
        st.info("No window data to plot.")
        return
    replica_dots = _window_replica_dots(runs=runs, frontend_base=frontend_base)
    x_tickvals = sorted({int(s.x_value) for s in stats})
    fig = _build_window_figure(stats=stats, replica_dots=replica_dots, x_tickvals=x_tickvals)
    chart_event = st.plotly_chart(
        fig,
        width="stretch",
        key="cross_swap_window_accuracy_chart",
        on_select="rerun",
        selection_mode=("points",),
    )
    _maybe_open_clicked_run(chart_event=chart_event)


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
    frontend_base = _render_frontend_base()
    pairs = _distinct_source_pairs(runs=all_cross_swap)
    chosen_pair = _render_source_pair_selector(pairs=pairs)
    pair_runs = [
        run
        for run in all_cross_swap
        if run.source_a_run_id == chosen_pair.source_a_run_id
        and run.source_b_run_id == chosen_pair.source_b_run_id
    ]
    if not pair_runs:
        st.info("No cross-swap runs match the selected source pair.")
        return
    selected_buckets = _bucket_filter(runs=pair_runs)
    if not selected_buckets:
        st.info("Select at least one cross-swap bucket.")
        return
    filtered = [r for r in pair_runs if r.swapped_series_key() in selected_buckets]
    if not filtered:
        st.info("No cross-swap runs match the selected buckets.")
        return
    st.markdown(f"### {chosen_pair.label()}")
    _render_window_view(runs=filtered, frontend_base=frontend_base)
    _render_included_runs(runs=filtered)
