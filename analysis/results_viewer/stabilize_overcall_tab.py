"""Streamlit tab surfacing veyru runs where the field observer over-called ``stabilize_veyru``.

Each run's call count is normalized by its number of problems (total case stages
across all rounds, times the team count), so ``calls per problem = 1.0`` is a
perfectly calibrated run and ``> 1.0`` is over-calling. Two radios drive the
headline metric: the **aggregation** toggle switches between the whole-simulation
ratio and the worst single round (so a run that over-calls in just one round is
not hidden by a calibrated average), and the **numerator** toggle switches
between all calls and redundant calls only -- the latter excludes failed retries
(``rejected``), which are legitimate struggles on a still-open stage rather than
over-calling.
"""

from typing import NamedTuple

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import render_frontend_base, run_url
from analysis.results_viewer.stabilize_overcall_data import (
    StabilizeOvercallRun,
    distinct_labels,
    load_overcall_runs,
    run_metric,
    worst_round,
)

_AGG_WHOLE = "Whole simulation (avg)"
_AGG_WORST = "Worst single round (max)"
_NUM_ALL = "All calls"
_NUM_REDUNDANT = "Redundant calls only (excludes failed retries)"


def _render_label_filter(runs: list[StabilizeOvercallRun]) -> list[str]:
    """Multiselect of every label present; an empty selection means no label filter."""
    return st.multiselect(
        label="Labels (run must carry all selected)",
        options=distinct_labels(runs=runs),
        default=[],
        key="overcall_label_filter",
    )


def _render_model_filter(runs: list[StabilizeOvercallRun]) -> list[str]:
    """Multiselect of every model present; an empty selection means no model filter."""
    return st.multiselect(
        label="Models",
        options=sorted({run.model for run in runs}),
        default=[],
        key="overcall_model_filter",
    )


def _apply_filters(
    runs: list[StabilizeOvercallRun],
    selected_labels: list[str],
    selected_models: list[str],
) -> list[StabilizeOvercallRun]:
    """Keep runs carrying every selected label and matching one of the selected models."""
    label_set = set(selected_labels)
    model_set = set(selected_models)
    out: list[StabilizeOvercallRun] = []
    for run in runs:
        if label_set and not label_set.issubset(set(run.labels)):
            continue
        if model_set and run.model not in model_set:
            continue
        out.append(run)
    return out


def _render_metric_controls() -> tuple[bool, bool]:
    """Two radios returning ``(use_redundant, worst_round)`` for the selected metric."""
    agg_col, num_col = st.columns(2)
    with agg_col:
        aggregation = st.radio(
            label="Aggregation",
            options=[_AGG_WHOLE, _AGG_WORST],
            index=0,
            key="overcall_aggregation",
            help="Worst single round surfaces runs that over-call in one round but look "
            "calibrated on average.",
        )
    with num_col:
        numerator = st.radio(
            label="Numerator",
            options=[_NUM_ALL, _NUM_REDUNDANT],
            index=0,
            key="overcall_numerator",
            help="Redundant = calls made when nothing needed stabilizing (case already "
            "stabilized / collapsed). Excludes failed retries on an open stage.",
        )
    return numerator == _NUM_REDUNDANT, aggregation == _AGG_WORST


def _metric_label(use_redundant: bool, by_worst_round: bool) -> str:
    """Human-readable name of the selected metric for axis titles and headers."""
    if use_redundant:
        numerator = "redundant calls per problem"
    else:
        numerator = "calls per problem"
    if by_worst_round:
        return f"{numerator} (worst round)"
    return numerator


def _reference_ratio(use_redundant: bool) -> float:
    """Ideal ratio for the selected numerator: 1 call/problem, or 0 redundant calls."""
    if use_redundant:
        return 0.0
    return 1.0


def _render_summary(
    runs: list[StabilizeOvercallRun],
    use_redundant: bool,
    by_worst_round: bool,
) -> None:
    """Headline metrics: run count, over-caller count, mean ratio, worst ratio."""
    ratios = [
        run_metric(run=run, use_redundant=use_redundant, worst_round=by_worst_round) for run in runs
    ]
    reference = _reference_ratio(use_redundant=use_redundant)
    over_callers = sum(1 for ratio in ratios if ratio > reference)
    mean_ratio = sum(ratios) / len(ratios)
    worst = max(ratios)
    col_runs, col_over, col_mean, col_worst = st.columns(4)
    col_runs.metric(label="Runs", value=len(runs))
    col_over.metric(label=f"Over-callers (> {reference:g})", value=over_callers)
    col_mean.metric(label="Mean ratio", value=f"{mean_ratio:.3f}")
    col_worst.metric(label="Max ratio", value=f"{worst:.3f}")


def _render_histogram(
    runs: list[StabilizeOvercallRun],
    use_redundant: bool,
    by_worst_round: bool,
) -> None:
    """Distribution of the selected ratio with an ideal-ratio reference line."""
    ratios = [
        run_metric(run=run, use_redundant=use_redundant, worst_round=by_worst_round) for run in runs
    ]
    reference = _reference_ratio(use_redundant=use_redundant)
    fig = go.Figure(
        data=go.Histogram(
            x=ratios,
            nbinsx=40,
            marker={"color": "#1f77b4"},
            hovertemplate="ratio=%{x:.3f}<br>runs=%{y}<extra></extra>",
        )
    )
    fig.add_vline(
        x=reference,
        line_width=2,
        line_dash="dash",
        line_color="#d62728",
        annotation_text=f"ideal = {reference:g}",
    )
    fig.update_layout(
        height=320,
        xaxis_title=_metric_label(use_redundant=use_redundant, by_worst_round=by_worst_round),
        yaxis_title="runs",
        margin={"l": 60, "r": 20, "t": 20, "b": 50},
        bargap=0.05,
    )
    st.plotly_chart(fig, width="stretch", key="overcall_histogram")


class _TableRow(NamedTuple):
    """One per-run dataframe row; worst-round fields are ``None`` in whole-sim mode."""

    ratio: float
    run_id: str
    model: str
    mode: str
    problems: int
    calls: int
    accepted: int
    rejected_retries: int
    redundant: int
    worst_round: int | None
    worst_round_calls: int | None
    worst_round_redundant: int | None
    labels: str
    url: str


def _build_table_row(
    run: StabilizeOvercallRun,
    use_redundant: bool,
    by_worst_round: bool,
    frontend_base: str,
) -> _TableRow:
    """Assemble one ``_TableRow``, filling worst-round detail when in that mode."""
    worst_number: int | None = None
    worst_calls: int | None = None
    worst_redundant: int | None = None
    if by_worst_round:
        observation = worst_round(run=run, use_redundant=use_redundant)
        if observation is not None:
            worst_number = observation.round_number
            worst_calls = observation.calls
            worst_redundant = observation.unjudged
    return _TableRow(
        ratio=round(
            run_metric(run=run, use_redundant=use_redundant, worst_round=by_worst_round), 3
        ),
        run_id=run.run_id,
        model=run.model,
        mode=run.mode,
        problems=run.problems,
        calls=run.calls,
        accepted=run.accepted,
        rejected_retries=run.rejected,
        redundant=run.unjudged,
        worst_round=worst_number,
        worst_round_calls=worst_calls,
        worst_round_redundant=worst_redundant,
        labels=", ".join(run.labels),
        url=run_url(frontend_base=frontend_base, run_id=run.run_id),
    )


def _render_table(
    runs: list[StabilizeOvercallRun],
    use_redundant: bool,
    by_worst_round: bool,
    frontend_base: str,
) -> None:
    """Sortable per-run table (selected ratio descending) with a clickable run link."""
    ordered = sorted(
        runs,
        key=lambda run: run_metric(
            run=run, use_redundant=use_redundant, worst_round=by_worst_round
        ),
        reverse=True,
    )
    rows = []
    for run in ordered:
        row = _build_table_row(
            run=run,
            use_redundant=use_redundant,
            by_worst_round=by_worst_round,
            frontend_base=frontend_base,
        )._asdict()
        if not by_worst_round:
            del row["worst_round"]
            del row["worst_round_calls"]
            del row["worst_round_redundant"]
        rows.append(row)
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "url": st.column_config.LinkColumn(
                label="open",
                display_text="↗",
                help="Open this run in the schmidt frontend",
            ),
        },
    )


def _render_drilldown(runs: list[StabilizeOvercallRun]) -> None:
    """Per-round expected stages vs the accepted / rejected / redundant call split."""
    st.markdown("### Per-round breakdown")
    run_ids = [run.run_id for run in runs]
    selected_id = st.selectbox(
        label="Run",
        options=run_ids,
        index=0,
        key="overcall_drilldown_run",
    )
    selected = next(run for run in runs if run.run_id == selected_id)
    rounds = [observation.round_number for observation in selected.per_round]
    expected = [observation.stages * selected.num_teams for observation in selected.per_round]
    fig = go.Figure()
    fig.add_bar(
        x=rounds,
        y=[observation.accepted for observation in selected.per_round],
        name="accepted",
        marker={"color": "#2ca02c"},
    )
    fig.add_bar(
        x=rounds,
        y=[observation.rejected for observation in selected.per_round],
        name="rejected (retries)",
        marker={"color": "#ff7f0e"},
    )
    fig.add_bar(
        x=rounds,
        y=[observation.unjudged for observation in selected.per_round],
        name="redundant",
        marker={"color": "#d62728"},
    )
    fig.add_scatter(
        x=rounds,
        y=expected,
        name="expected (problems)",
        mode="markers",
        marker={"color": "#000000", "symbol": "line-ew-open", "size": 14, "line": {"width": 3}},
    )
    fig.update_layout(
        barmode="stack",
        height=380,
        xaxis_title="round",
        yaxis_title="stabilize_veyru calls",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        margin={"l": 60, "r": 20, "t": 40, "b": 50},
    )
    st.plotly_chart(fig, width="stretch", key="overcall_drilldown_chart")


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Stabilize over-calling tab body."""
    st.caption(
        "Normalized over-calling for veyru runs. Denominator = total case stages × team count "
        "(one case per round, 1-5 stages each). A call that hits no open stage (case already "
        "stabilized / collapsed) is *redundant*; a judge-rejected call is a *retry* on a "
        "still-open stage. Runs with injected cases (`veyru_case_overridden`) may have "
        "approximate problem counts."
    )
    runs = load_overcall_runs(evaluated=evaluated)
    if not runs:
        st.info("No evaluated veyru runs found.")
        return
    use_redundant, by_worst_round = _render_metric_controls()
    selected_labels = _render_label_filter(runs=runs)
    selected_models = _render_model_filter(runs=runs)
    frontend_base = render_frontend_base(streamlit_key="overcall_frontend_base")
    filtered = _apply_filters(
        runs=runs,
        selected_labels=selected_labels,
        selected_models=selected_models,
    )
    if not filtered:
        st.info("No veyru runs match the selected filters.")
        return
    _render_summary(runs=filtered, use_redundant=use_redundant, by_worst_round=by_worst_round)
    _render_histogram(runs=filtered, use_redundant=use_redundant, by_worst_round=by_worst_round)
    _render_table(
        runs=filtered,
        use_redundant=use_redundant,
        by_worst_round=by_worst_round,
        frontend_base=frontend_base,
    )
    _render_drilldown(runs=filtered)
