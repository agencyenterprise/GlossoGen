"""Streamlit tab plotting resume runs against their source runs.

X = round_start, Y = mean fraction of post-swap rounds stabilized. One solid
line per replacement model and a matched dashed line for what the source
achieved over the same window. Every run with a ``replace_manifest.json`` is
eligible (no label required); a Multi-swap subtab shows resumes whose JSONL
fired at least one ``AgentSwappedMidRun`` event, and a No-swap subtab shows
the rest.
"""

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.resume_data import ResumeRun, list_resume_runs
from analysis.results_viewer.resume_multi_swap_view import render as render_multi_swap_subtab
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import maybe_open_clicked_run, render_frontend_base, run_url
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


def _scenarios_with_resume_runs(runs: list[ResumeRun]) -> list[str]:
    """Return every scenario that has at least one resume run.

    Auto-discovered from the loaded resume runs so a new scenario that
    starts using replace-agent shows up in the selector for free.
    """
    return sorted({run.scenario_name for run in runs})


def _render_scenario_selector(runs: list[ResumeRun]) -> str | None:
    """Radio selector listing every scenario with at least one resume run."""
    options = _scenarios_with_resume_runs(runs=runs)
    if not options:
        return None
    chosen = st.radio(
        label="Scenario",
        options=options,
        index=0,
        horizontal=True,
        key="resume_scenario_selector",
    )
    return chosen


def _bucket_filter(runs: list[ResumeRun], key_prefix: str) -> set[str]:
    """One checkbox per distinct resume-bucket key; returns selected keys.

    ``key_prefix`` namespaces the underlying ``st.checkbox`` keys so the same
    bucket label rendered in two parallel subtabs gets independent state.
    """
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
            key=f"{key_prefix}_bucket_filter::{name}",
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
    frontend_base: str,
) -> dict[str, tuple[list[float], list[float], list[str], list[str]]]:
    """Per-series jittered (round_start, accuracy) replica points + URL for the window chart.

    Resumed dots link to the resumed run; source dots link to the matched
    source run so users can open either side of the comparison.
    """
    dots: dict[str, tuple[list[float], list[float], list[str], list[str]]] = {}
    counter: dict[str, int] = {}
    for run in runs:
        for series, value, target_run_id in (
            (_window_resumed_series(run=run), _resumed_window_accuracy(run=run), run.run_id),
            (
                _window_source_series(run=run),
                _source_window_accuracy(run=run),
                run.source_run_id,
            ),
        ):
            if value is None:
                continue
            bucket = dots.setdefault(series, ([], [], [], []))
            index = counter.get(series, 0)
            bucket[0].append(jittered_x_linear(base_x=float(run.round_start), index=index))
            bucket[1].append(value)
            url = run_url(frontend_base=frontend_base, run_id=target_run_id)
            bucket[2].append(
                f"{target_run_id}<br>{series}<br>round_start={run.round_start}<br>"
                f"accuracy={value:.3f}<br>click to open · {url}"
            )
            bucket[3].append(url)
            counter[series] = index + 1
    return dots


def _build_window_figure(
    stats: list[SeriesStats],
    replica_dots: dict[str, tuple[list[float], list[float], list[str], list[str]]],
    x_tickvals: list[int],
) -> go.Figure:
    """Per-window-accuracy figure: X = round_start, Y = mean fraction stabilized."""
    fig = go.Figure()
    series_keys = sorted({s.series for s in stats})
    palette = series_color_map(series_keys=series_keys)
    stats_by_series: dict[str, list[SeriesStats]] = {}
    for stat in stats:
        stats_by_series.setdefault(stat.series, []).append(stat)
    # Means are drawn first so the replica scatter sits on top and click events
    # land on replica points (which carry the per-run customdata URL) rather
    # than the larger opaque mean markers.
    for series, colour in palette.items():
        dash = "dash" if series.endswith(" · source") else "solid"
        add_mean_trace(
            fig=fig,
            series=series,
            stats=stats_by_series[series],
            metric_display_name="window accuracy",
            colour=colour,
            dash=dash,
        )
    for series, colour in palette.items():
        xs, ys, hover, urls = replica_dots.get(series, ([], [], [], []))
        if xs:
            add_replica_trace(
                fig=fig,
                series=series,
                xs=xs,
                ys=ys,
                hover_texts=hover,
                colour=colour,
                customdata=urls,
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


def _render_window_view(runs: list[ResumeRun], frontend_base: str, key_prefix: str) -> None:
    """Render the per-window aggregate accuracy chart + caption.

    ``key_prefix`` namespaces the Plotly chart key and click-tracking session
    key so parallel subtabs each get their own widget state.
    """
    st.caption(
        "Per replica, mean success across the rounds it actually played; "
        "the dashed line is what the source achieved over the same rounds."
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
        key=f"{key_prefix}_window_accuracy_chart",
        on_select="rerun",
        selection_mode=("points",),
    )
    maybe_open_clicked_run(
        chart_event=chart_event,
        session_key=f"{key_prefix}_last_opened_url",
    )


def _render_included_runs(runs: list[ResumeRun], frontend_base: str) -> None:
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
            "url": run_url(frontend_base=frontend_base, run_id=run.run_id),
            "source_url": run_url(frontend_base=frontend_base, run_id=run.source_run_id),
        }
        for run in sorted(runs, key=lambda r: (r.resumed_series_key(), r.run_id))
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
                    help="Open this resumed run in the schmidt frontend",
                ),
                "source_url": st.column_config.LinkColumn(
                    label="open source",
                    display_text="↗",
                    help="Open the matched source run in the schmidt frontend",
                ),
            },
        )


def _render_subtab(
    runs: list[ResumeRun],
    frontend_base: str,
    key_prefix: str,
    empty_message: str,
) -> None:
    """Render a single Resume subtab: bucket filter + window chart + audit table.

    ``key_prefix`` namespaces every Streamlit widget key inside the subtab
    (bucket checkboxes, chart key, click-tracking session key) so the two
    parallel subtabs maintain independent widget state.
    """
    if not runs:
        st.info(empty_message)
        return
    selected_buckets = _bucket_filter(runs=runs, key_prefix=key_prefix)
    if not selected_buckets:
        st.info("Select at least one resume bucket.")
        return
    filtered = [r for r in runs if r.resumed_series_key() in selected_buckets]
    if not filtered:
        st.info("No resume runs match the selected buckets.")
        return
    _render_window_view(runs=filtered, frontend_base=frontend_base, key_prefix=key_prefix)
    _render_included_runs(runs=filtered, frontend_base=frontend_base)


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Resume tab body with Multi-swap and No-swap subtabs."""
    all_resume = list_resume_runs(evaluated_runs=evaluated)
    if not all_resume:
        st.info(
            "No runs with a `replace_manifest.json` found. "
            "Launch `schmidt replace-agent`, `schmidt cross-run-replace-agent`, "
            "or `schmidt resume-at-round` to populate this tab."
        )
        return
    scenario_name = _render_scenario_selector(runs=all_resume)
    if scenario_name is None:
        st.info("No scenarios with resume-labeled runs found.")
        return
    scenario_runs = [r for r in all_resume if r.scenario_name == scenario_name]
    if not scenario_runs:
        st.info(f"No resume runs in scenario `{scenario_name}`.")
        return
    frontend_base = render_frontend_base(streamlit_key="resume_frontend_base")

    multi_swap_panel, no_swap_panel = st.tabs(["Multi-swap", "No swap"])
    with multi_swap_panel:
        render_multi_swap_subtab(
            multi_swap_resumes=[r for r in scenario_runs if r.has_in_run_swaps],
            evaluated=evaluated,
            frontend_base=frontend_base,
            key_prefix="resume_multi",
        )
    with no_swap_panel:
        _render_subtab(
            runs=[r for r in scenario_runs if not r.has_in_run_swaps],
            frontend_base=frontend_base,
            key_prefix="resume_no_swap",
            empty_message=(f"No resume runs without in-run swaps in scenario `{scenario_name}`."),
        )
