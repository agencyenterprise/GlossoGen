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

from analysis.results_viewer import judge_replay_filter, seed_mode_filter
from analysis.results_viewer.cross_swap_data import CrossSwapRun, list_cross_swap_runs
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import render_frontend_base, run_url
from analysis.results_viewer.scenario_selector import render_scenario_radio
from analysis.results_viewer.series_plot import (
    SeriesStats,
    add_mean_trace,
    add_replica_trace,
    jittered_x_linear,
    series_color_map,
)


def _scenarios_with_cross_swap_runs(runs: list[CrossSwapRun]) -> list[str]:
    """Return every scenario with at least one cross-swap run.

    Auto-discovered from the loaded cross-swap runs.
    """
    return sorted({run.scenario_name for run in runs})


def _render_scenario_selector(runs: list[CrossSwapRun]) -> str | None:
    """Radio selector listing every scenario with at least one cross-swap run."""
    options = _scenarios_with_cross_swap_runs(runs=runs)
    return render_scenario_radio(options=options, key="cross_swap_scenario_selector")


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
        swapped_url = run_url(frontend_base=frontend_base, run_id=run.run_id)
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
            url = run_url(frontend_base=frontend_base, run_id=source_run_id)
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


def _swapped_per_round_means(
    runs: list[CrossSwapRun],
) -> dict[int, dict[int, float]]:
    """Per ``round_start``, mean post-swap success at each round across replicas."""
    grouped: dict[int, list[CrossSwapRun]] = {}
    for run in runs:
        grouped.setdefault(run.round_start, []).append(run)
    means: dict[int, dict[int, float]] = {}
    for round_start, group in grouped.items():
        per_round: dict[int, list[float]] = {}
        for run in group:
            for round_number, succeeded in run.swapped_round_outcomes.items():
                per_round.setdefault(round_number, []).append(1.0 if succeeded else 0.0)
        means[round_start] = {
            round_number: sum(values) / len(values) for round_number, values in per_round.items()
        }
    return means


def _source_per_round_step(outcomes: dict[int, bool]) -> tuple[list[int], list[float]]:
    """Sorted ``(rounds, 0/1 values)`` for a single source run's outcomes."""
    rounds = sorted(outcomes)
    values = [1.0 if outcomes[round_number] else 0.0 for round_number in rounds]
    return rounds, values


_TIMELINE_Y_OFFSET_STEP = 0.03


def _build_timeline_figure(runs: list[CrossSwapRun]) -> go.Figure:
    """Per-round timeline: source A & B outcomes plus per-round_start swapped mean.

    Each series is rendered with a small Y offset (multiples of
    ``_TIMELINE_Y_OFFSET_STEP``) so coincident lines at 0 or 1 don't hide
    each other. Hover restores the true value; the Y axis still ticks at 0
    and 1 so the floor/ceiling stay legible.
    """
    fig = go.Figure()
    sample = runs[0]
    source_a_label = f"{sample.source_a_replaced_agent_model} · source A"
    source_b_label = f"{sample.source_b_replaced_agent_model} · source B"
    swap_round_starts = sorted({run.round_start for run in runs})
    series_keys = [
        source_a_label,
        source_b_label,
        *[f"{sample.imported_model} · swapped @ R{rs}" for rs in swap_round_starts],
    ]
    palette = series_color_map(series_keys=series_keys)

    a_rounds, a_values = _source_per_round_step(outcomes=sample.source_a_round_outcomes)
    if a_rounds:
        offset = 0.0
        fig.add_trace(
            go.Scatter(
                x=a_rounds,
                y=[v + offset for v in a_values],
                customdata=a_values,
                mode="lines+markers",
                name=source_a_label,
                line=dict(color=palette[source_a_label], dash="dash", shape="hv"),
                marker=dict(size=6),
                hovertemplate=(
                    f"{sample.source_a_run_id}<br>round=%{{x}}<br>"
                    "stabilized=%{customdata:.0f}<extra></extra>"
                ),
            )
        )
    b_rounds, b_values = _source_per_round_step(outcomes=sample.source_b_round_outcomes)
    if b_rounds:
        offset = _TIMELINE_Y_OFFSET_STEP
        fig.add_trace(
            go.Scatter(
                x=b_rounds,
                y=[v + offset for v in b_values],
                customdata=b_values,
                mode="lines+markers",
                name=source_b_label,
                line=dict(color=palette[source_b_label], dash="dot", shape="hv"),
                marker=dict(size=6),
                hovertemplate=(
                    f"{sample.source_b_run_id}<br>round=%{{x}}<br>"
                    "stabilized=%{customdata:.0f}<extra></extra>"
                ),
            )
        )

    swap_means = _swapped_per_round_means(runs=runs)
    for index, round_start in enumerate(swap_round_starts):
        means_at_round = swap_means[round_start]
        rounds = sorted(means_at_round)
        values = [means_at_round[round_number] for round_number in rounds]
        offset = -_TIMELINE_Y_OFFSET_STEP * (index + 1)
        replica_count = sum(1 for run in runs if run.round_start == round_start)
        label = f"{sample.imported_model} · swapped @ R{round_start}"
        fig.add_trace(
            go.Scatter(
                x=rounds,
                y=[v + offset for v in values],
                customdata=values,
                mode="lines+markers",
                name=f"{label} (n={replica_count})",
                line=dict(color=palette[label], dash="solid"),
                marker=dict(size=7),
                hovertemplate=(
                    f"{label}<br>round=%{{x}}<br>"
                    "mean stabilized=%{customdata:.2f}<extra></extra>"
                ),
            )
        )
        fig.add_vline(
            x=round_start,
            line=dict(color=palette[label], width=1, dash="dot"),
            opacity=0.4,
        )

    all_rounds = sorted(
        set(a_rounds)
        | set(b_rounds)
        | {round_number for series in swap_means.values() for round_number in series}
    )
    max_offset_below = _TIMELINE_Y_OFFSET_STEP * len(swap_round_starts)
    max_offset_above = _TIMELINE_Y_OFFSET_STEP
    fig.update_layout(
        xaxis=dict(
            title="round",
            tickmode="array",
            tickvals=all_rounds,
            ticktext=[f"R{r}" for r in all_rounds],
        ),
        yaxis=dict(
            title="round stabilized (1.0=yes, 0.0=collapsed)",
            range=[-0.05 - max_offset_below, 1.05 + max_offset_above],
            tickmode="array",
            tickvals=[0.0, 0.25, 0.5, 0.75, 1.0],
            ticktext=["0", "0.25", "0.5", "0.75", "1"],
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=20, t=40, b=60),
        height=420,
    )
    return fig


def _render_timeline_view(runs: list[CrossSwapRun]) -> None:
    """Render the per-round timeline plot below the window-accuracy chart."""
    st.markdown("#### Round-by-round timeline")
    st.caption(
        "Source A (dashed) and source B (dotted) show per-round outcomes "
        "of the original simulations as 0/1 step lines — flat at 1 means "
        "stabilized, drops to 0 mark collapses. Solid lines are the swapped "
        "runs' mean stabilization rate per round, one line per ``round_start`` "
        "bucket. Vertical dotted lines mark each swap boundary. Each series "
        "is rendered with a small Y offset so coincident lines at 0 or 1 "
        "stay distinguishable; hover shows the true value."
    )
    fig = _build_timeline_figure(runs=runs)
    st.plotly_chart(fig, width="stretch", key="cross_swap_timeline_chart")


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
    ratio_map = judge_replay_filter.flip_ratio_by_run_id(evaluated=evaluated)
    run_filter = seed_mode_filter.render_filters(key_prefix="cross_swap")
    evaluated = seed_mode_filter.apply(evaluated=evaluated, run_filter=run_filter)
    all_cross_swap = list_cross_swap_runs(evaluated_runs=evaluated)
    if not all_cross_swap:
        st.info(
            "No runs labeled 'cross_team' found. "
            "Add the 'cross_team' label to cross-run replace-agent runs you want compared here."
        )
        return
    scenario_name = _render_scenario_selector(runs=all_cross_swap)
    if scenario_name is None:
        st.info("No scenarios with cross-swap-labeled runs found.")
        return
    scenario_runs = [r for r in all_cross_swap if r.scenario_name == scenario_name]
    if not scenario_runs:
        st.info(f"No cross-swap runs in scenario `{scenario_name}`.")
        return
    frontend_base = render_frontend_base(streamlit_key="cross_swap_frontend_base")
    pairs = _distinct_source_pairs(runs=scenario_runs)
    chosen_pair = _render_source_pair_selector(pairs=pairs)
    pair_runs = [
        run
        for run in scenario_runs
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
    filtered = judge_replay_filter.render_and_filter(
        items=filtered,
        ratio_of=lambda run: ratio_map.get(run.run_id),
        key="cross_swap",
        item_label="cross-swap runs",
    )
    if not filtered:
        st.info("All runs filtered out by judge-replay slider.")
        return
    st.markdown(f"### {chosen_pair.label()}")
    _render_window_view(runs=filtered, frontend_base=frontend_base)
    _render_timeline_view(runs=filtered)
    _render_included_runs(runs=filtered)
