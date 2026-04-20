"""Builds the Plotly timeline figure overlaying multiple runs' per-round hits."""

from typing import NamedTuple

import plotly.graph_objects as go

from analysis.results_viewer.event_extractor import RunTimeline, TimelineEventKind
from analysis.results_viewer.evidence_parser import extract_rounds_identified
from schmidt.evaluation.evaluation_report import EvaluationReport


class _ProminentStyle(NamedTuple):
    """Rendering attributes for events that get a vertical line + annotation."""

    colour: str
    dash: str
    width: int
    icon: str
    label_short: str


class _GlyphStyle(NamedTuple):
    """Rendering attributes for world-state events shown as glyphs on the events lane."""

    colour: str
    symbol: str
    label: str


_PROMINENT_STYLES: dict[TimelineEventKind, _ProminentStyle] = {
    TimelineEventKind.SWAP: _ProminentStyle(
        colour="#6f42c1", dash="solid", width=4, icon="↔", label_short="SWAP"
    ),
    TimelineEventKind.INTERN_TAKEOVER: _ProminentStyle(
        colour="#0b6b0b", dash="solid", width=4, icon="⇒", label_short="TAKEOVER"
    ),
    TimelineEventKind.INTERN_JOIN: _ProminentStyle(
        colour="#0969da", dash="dot", width=2, icon="+", label_short="INTERN"
    ),
}

_GLYPH_STYLES: dict[TimelineEventKind, _GlyphStyle] = {
    TimelineEventKind.COLLAPSE: _GlyphStyle(
        colour="#cf222e", symbol="x", label="Veyru collapsed"
    ),
    TimelineEventKind.STABILIZED: _GlyphStyle(
        colour="#1a7f37", symbol="star", label="Veyru stabilized"
    ),
    TimelineEventKind.POSTMORTEM_CLOSED: _GlyphStyle(
        colour="#9a6700", symbol="square-open", label="Postmortem closed"
    ),
}

_EVENTS_LANE_LABEL = "world events"

_RUN_PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#17becf",
    "#8c564b",
    "#e377c2",
]


class _RunPlotData(NamedTuple):
    """Derived per-run data needed to render a swimlane row per evaluator."""

    run_key: str
    total_rounds: int
    per_evaluator_rounds: dict[str, list[int]]
    timeline: RunTimeline


def collect_per_round_evaluators(reports: list[EvaluationReport]) -> list[str]:
    """Return the sorted union of evaluator names that produced per-round data."""
    names: set[str] = set()
    for report in reports:
        for metric in report.metrics:
            rounds = extract_rounds_identified(evidence=metric.evidence)
            if rounds:
                names.add(metric.evaluator_name)
    return sorted(names)


def _build_run_plot_data(
    run_key: str,
    report: EvaluationReport,
    timeline: RunTimeline,
) -> _RunPlotData:
    """Build the per-evaluator rounds mapping for one run."""
    per_evaluator: dict[str, list[int]] = {}
    for metric in report.metrics:
        rounds = extract_rounds_identified(evidence=metric.evidence)
        if rounds:
            per_evaluator[metric.evaluator_name] = rounds
    return _RunPlotData(
        run_key=run_key,
        total_rounds=timeline.total_rounds,
        per_evaluator_rounds=per_evaluator,
        timeline=timeline,
    )


def _add_run_trace(
    fig: go.Figure,
    run: _RunPlotData,
    evaluators: list[str],
    run_index: int,
    run_count: int,
    colour: str,
) -> None:
    """Add one marker trace per run, offset vertically so overlapping runs don't hide dots."""
    if run_count == 1:
        offset = 0.0
    else:
        offset = (run_index - (run_count - 1) / 2) * 0.18
    xs: list[int] = []
    ys: list[float] = []
    hover: list[str] = []
    for eval_name, rounds in run.per_evaluator_rounds.items():
        if eval_name not in evaluators:
            continue
        base_y = evaluators.index(eval_name)
        for rnd in rounds:
            xs.append(rnd)
            ys.append(base_y + offset)
            hover.append(f"<b>{run.run_key}</b><br>{eval_name}<br>round {rnd}")
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            marker=dict(color=colour, size=13, line=dict(width=1, color="white")),
            name=run.run_key,
            legendgroup="runs",
            legendgrouptitle=dict(text="Runs"),
            hovertext=hover,
            hoverinfo="text",
        )
    )


def _dedup_prominent_events(
    runs: list[_RunPlotData],
) -> dict[tuple[TimelineEventKind, int], list[str]]:
    """Collect which runs triggered each prominent event at a given round."""
    grouped: dict[tuple[TimelineEventKind, int], list[str]] = {}
    for run in runs:
        for event in run.timeline.events:
            if event.kind not in _PROMINENT_STYLES:
                continue
            key = (event.kind, event.round_number)
            grouped.setdefault(key, []).append(run.run_key)
    return grouped


def _add_prominent_events(fig: go.Figure, runs: list[_RunPlotData]) -> None:
    """Render swap/intern events as vertical lines with a single annotation per round."""
    grouped = _dedup_prominent_events(runs=runs)
    for (kind, rnd), run_keys in grouped.items():
        style = _PROMINENT_STYLES[kind]
        fig.add_vrect(
            x0=rnd - 0.22,
            x1=rnd + 0.22,
            fillcolor=style.colour,
            opacity=0.12,
            line_width=0,
        )
        fig.add_vline(
            x=rnd,
            line=dict(color=style.colour, dash=style.dash, width=style.width),
            opacity=0.9,
            annotation_text=f"<b>{style.icon} {style.label_short}</b>",
            annotation_position="top",
            annotation=dict(
                font=dict(size=13, color=style.colour, family="sans-serif"),
                bgcolor="rgba(255,255,255,0.9)",
                bordercolor=style.colour,
                borderwidth=1,
                hovertext="Runs: " + ", ".join(run_keys),
            ),
        )


def _collect_glyph_points(
    runs: list[_RunPlotData],
    events_lane_y: float,
    run_offsets: dict[str, float],
) -> dict[TimelineEventKind, tuple[list[float], list[float], list[str]]]:
    """Bucket world-state events by kind, with hover text listing the originating run."""
    buckets: dict[TimelineEventKind, tuple[list[float], list[float], list[str]]] = {
        kind: ([], [], []) for kind in _GLYPH_STYLES.keys()
    }
    for run in runs:
        offset = run_offsets[run.run_key]
        for event in run.timeline.events:
            if event.kind not in _GLYPH_STYLES:
                continue
            xs, ys, hover = buckets[event.kind]
            xs.append(event.round_number)
            ys.append(events_lane_y + offset)
            hover.append(f"<b>{run.run_key}</b><br>{_GLYPH_STYLES[event.kind].label}")
    return buckets


def _add_world_glyphs(
    fig: go.Figure,
    runs: list[_RunPlotData],
    events_lane_y: float,
) -> None:
    """Render world-state events on the dedicated events lane as shaped glyphs."""
    run_count = len(runs)
    run_offsets: dict[str, float] = {}
    for index, run in enumerate(runs):
        if run_count == 1:
            run_offsets[run.run_key] = 0.0
        else:
            run_offsets[run.run_key] = (index - (run_count - 1) / 2) * 0.18
    buckets = _collect_glyph_points(
        runs=runs, events_lane_y=events_lane_y, run_offsets=run_offsets
    )
    for kind, (xs, ys, hover) in buckets.items():
        if not xs:
            continue
        style = _GLYPH_STYLES[kind]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                marker=dict(
                    color=style.colour,
                    symbol=style.symbol,
                    size=14,
                    line=dict(width=1.5, color=style.colour),
                ),
                name=style.label,
                legendgroup="events",
                legendgrouptitle=dict(text="World events"),
                hovertext=hover,
                hoverinfo="text",
            )
        )


def build_timeline_figure(
    reports: dict[str, EvaluationReport],
    timelines: dict[str, RunTimeline],
    evaluators: list[str],
) -> go.Figure:
    """Build the overlay timeline figure.

    ``reports`` and ``timelines`` are keyed by the same short run identifier.
    ``evaluators`` is the ordered list of evaluator names to render as lanes.
    """
    run_keys = list(reports.keys())
    if not evaluators:
        fig = go.Figure()
        fig.update_layout(
            annotations=[
                dict(
                    text="No evaluators selected (or none have per-round evidence).",
                    showarrow=False,
                    x=0.5,
                    y=0.5,
                    xref="paper",
                    yref="paper",
                )
            ]
        )
        return fig

    run_plot_data = [
        _build_run_plot_data(run_key=key, report=reports[key], timeline=timelines[key])
        for key in run_keys
    ]
    max_round = max((r.total_rounds for r in run_plot_data), default=1)

    fig = go.Figure()
    for index, run in enumerate(run_plot_data):
        colour = _RUN_PALETTE[index % len(_RUN_PALETTE)]
        _add_run_trace(
            fig=fig,
            run=run,
            evaluators=evaluators,
            run_index=index,
            run_count=len(run_plot_data),
            colour=colour,
        )

    events_lane_y = -1.2
    _add_world_glyphs(fig=fig, runs=run_plot_data, events_lane_y=events_lane_y)
    _add_prominent_events(fig=fig, runs=run_plot_data)

    tickvals = [events_lane_y, *range(len(evaluators))]
    ticktext = [_EVENTS_LANE_LABEL, *evaluators]

    fig.update_layout(
        title=dict(text="Per-round evaluator hits with scenario events", x=0.01, xanchor="left"),
        xaxis=dict(
            title="Round",
            tickmode="linear",
            dtick=1,
            range=[0.5, max_round + 0.5],
            showgrid=True,
            gridcolor="rgba(0,0,0,0.08)",
        ),
        yaxis=dict(
            title="",
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext,
            range=[events_lane_y - 0.6, len(evaluators) - 0.4],
            showgrid=True,
            gridcolor="rgba(0,0,0,0.04)",
        ),
        height=220 + 90 * len(evaluators),
        hovermode="closest",
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1.0,
            xanchor="left",
            x=1.02,
            groupclick="toggleitem",
        ),
        margin=dict(l=160, r=260, t=110, b=60),
        plot_bgcolor="white",
    )
    return fig
