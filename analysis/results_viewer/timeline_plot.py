"""Builds the Plotly timeline figure overlaying multiple runs' per-round hits."""

from typing import NamedTuple

import plotly.graph_objects as go

from analysis.results_viewer.event_extractor import RunTimeline, TimelineEventKind
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
    TimelineEventKind.COLLAPSE: _GlyphStyle(colour="#cf222e", symbol="x", label="Veyru collapsed"),
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
    """Return the sorted union of evaluator names present in the reports.

    Every evaluator now reports ``rounds_identified`` as a structured field on
    ``MetricResult``; lanes appear for all evaluators that ran, even when a run
    produced zero round hits.
    """
    names: set[str] = set()
    for report in reports:
        for metric in report.metrics:
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
        if metric.rounds_identified:
            per_evaluator[metric.evaluator_name] = sorted(metric.rounds_identified)
    return _RunPlotData(
        run_key=run_key,
        total_rounds=timeline.total_rounds,
        per_evaluator_rounds=per_evaluator,
        timeline=timeline,
    )


def _run_vertical_offset(run_index: int, run_count: int) -> float:
    """Vertical jitter so overlapping run markers remain visible."""
    if run_count == 1:
        return 0.0
    return (run_index - (run_count - 1) / 2) * 0.18


_INTERMEDIATE_STEPS_PER_UNIT = 8


def _nearest_round(value: float, rounds: list[int]) -> int:
    """Return the round in ``rounds`` that is closest to ``value``."""
    return min(rounds, key=lambda r: abs(r - value))


def _build_click_overlay(
    run_key: str, evaluator_name: str, sorted_rounds: list[int], y: float
) -> tuple[list[float], list[float], list[list[object]]]:
    """Dense transparent markers along the line so clicks on the line open the modal."""
    overlay_xs: list[float] = []
    overlay_ys: list[float] = []
    overlay_cd: list[list[object]] = []
    for index in range(len(sorted_rounds) - 1):
        start_round = sorted_rounds[index]
        end_round = sorted_rounds[index + 1]
        gap = end_round - start_round
        steps = max(1, int(gap * _INTERMEDIATE_STEPS_PER_UNIT))
        for step in range(1, steps):
            x = start_round + gap * (step / steps)
            nearest = _nearest_round(value=x, rounds=sorted_rounds)
            overlay_xs.append(x)
            overlay_ys.append(y)
            overlay_cd.append([run_key, evaluator_name, nearest])
    return overlay_xs, overlay_ys, overlay_cd


def _add_run_trace(
    fig: go.Figure,
    run: _RunPlotData,
    evaluators: list[str],
    run_index: int,
    run_count: int,
    colour: str,
) -> None:
    """Add one dots+lines trace per (run, evaluator lane); legend shows the run once.

    Each visible dot carries ``customdata = [run_key, evaluator_name, round]``. Transparent
    intermediate markers are added along the connecting line so clicks on the line segment
    also open the modal (mapped to the nearest real round).
    """
    offset = _run_vertical_offset(run_index=run_index, run_count=run_count)
    legend_shown = False
    for eval_name in evaluators:
        rounds = run.per_evaluator_rounds.get(eval_name)
        if not rounds:
            continue
        base_y = evaluators.index(eval_name)
        y = base_y + offset
        sorted_rounds = sorted(rounds)
        ys = [y] * len(sorted_rounds)
        customdata = [[run.run_key, eval_name, r] for r in sorted_rounds]
        show_legend = not legend_shown
        legend_shown = True
        fig.add_trace(
            go.Scatter(
                x=sorted_rounds,
                y=ys,
                mode="markers+lines",
                marker=dict(color=colour, size=13, line=dict(width=1, color="white")),
                line=dict(color=colour, width=2),
                name=run.run_key,
                legendgroup=f"run::{run.run_key}",
                legendgrouptitle=dict(text="Runs"),
                showlegend=show_legend,
                hoverinfo="none",
                customdata=customdata,
                selected=dict(marker=dict(opacity=1, size=13, color=colour)),
                unselected=dict(marker=dict(opacity=1, size=13, color=colour)),
            )
        )
        overlay_xs, overlay_ys, overlay_cd = _build_click_overlay(
            run_key=run.run_key,
            evaluator_name=eval_name,
            sorted_rounds=sorted_rounds,
            y=y,
        )
        if not overlay_xs:
            continue
        fig.add_trace(
            go.Scatter(
                x=overlay_xs,
                y=overlay_ys,
                mode="markers",
                marker=dict(color=colour, size=14, opacity=0.0001),
                name=f"{run.run_key} click overlay",
                legendgroup=f"run::{run.run_key}",
                showlegend=False,
                hoverinfo="none",
                customdata=overlay_cd,
                selected=dict(marker=dict(opacity=0.0001, size=14, color=colour)),
                unselected=dict(marker=dict(opacity=0.0001, size=14, color=colour)),
            )
        )


def _build_run_colors(runs: list[_RunPlotData]) -> dict[str, str]:
    """Assign each run a stable colour from the run palette."""
    return {run.run_key: _RUN_PALETTE[index % len(_RUN_PALETTE)] for index, run in enumerate(runs)}


def palette_color_for_index(index: int) -> str:
    """Return the palette colour that ``build_timeline_figure`` assigns to run #``index``."""
    return _RUN_PALETTE[index % len(_RUN_PALETTE)]


def _compute_run_x_offsets(run_count: int) -> list[float]:
    """Horizontal offsets so vertical event lines from multiple runs don't overlap."""
    if run_count == 1:
        return [0.0]
    return [(index - (run_count - 1) / 2) * 0.12 for index in range(run_count)]


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


def _add_prominent_events(
    fig: go.Figure,
    runs: list[_RunPlotData],
    run_colors: dict[str, str],
) -> None:
    """Vertical swap/intern lines coloured per run; one top annotation per (kind, round)."""
    x_offsets = _compute_run_x_offsets(run_count=len(runs))
    for run_index, run in enumerate(runs):
        x_off = x_offsets[run_index]
        run_colour = run_colors[run.run_key]
        for event in run.timeline.events:
            style = _PROMINENT_STYLES.get(event.kind)
            if style is None:
                continue
            fig.add_vline(
                x=event.round_number + x_off,
                line=dict(color=run_colour, dash=style.dash, width=style.width),
                opacity=0.9,
            )
    for (kind, rnd), run_keys in _dedup_prominent_events(runs=runs).items():
        style = _PROMINENT_STYLES[kind]
        fig.add_annotation(
            x=rnd,
            y=1.0,
            xref="x",
            yref="paper",
            text=f"<b>{style.icon} {style.label_short}</b>",
            showarrow=False,
            yshift=6,
            font=dict(size=12, color=style.colour, family="sans-serif"),
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor=style.colour,
            borderwidth=1,
            hovertext="Runs: " + ", ".join(run_keys),
        )


def _add_world_glyphs(
    fig: go.Figure,
    runs: list[_RunPlotData],
    events_lane_y: float,
    run_colors: dict[str, str],
) -> None:
    """Render world-state events as per-run markers: colour = run, symbol = event kind."""
    run_count = len(runs)
    for index, run in enumerate(runs):
        if run_count == 1:
            offset = 0.0
        else:
            offset = (index - (run_count - 1) / 2) * 0.18
        xs: list[float] = []
        ys: list[float] = []
        symbols: list[str] = []
        hover: list[str] = []
        for event in run.timeline.events:
            style = _GLYPH_STYLES.get(event.kind)
            if style is None:
                continue
            xs.append(event.round_number)
            ys.append(events_lane_y + offset)
            symbols.append(style.symbol)
            hover.append(f"<b>{run.run_key}</b><br>{style.label}")
        if not xs:
            continue
        colour = run_colors[run.run_key]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                marker=dict(
                    color=colour,
                    symbol=symbols,
                    size=14,
                    line=dict(width=1.5, color=colour),
                ),
                name=f"{run.run_key} events",
                legendgroup="runs",
                showlegend=False,
                hovertext=hover,
                hoverinfo="text",
                selected=dict(marker=dict(opacity=1, size=14, color=colour)),
                unselected=dict(marker=dict(opacity=1, size=14, color=colour)),
            )
        )
    for style in _GLYPH_STYLES.values():
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker=dict(
                    color="rgba(80,80,80,0.85)",
                    symbol=style.symbol,
                    size=14,
                    line=dict(width=1.5, color="rgba(80,80,80,0.85)"),
                ),
                name=style.label,
                legendgroup="events",
                legendgrouptitle=dict(text="World events"),
                hoverinfo="skip",
                showlegend=True,
            )
        )


def build_timeline_figure(
    reports: dict[str, EvaluationReport],
    timelines: dict[str, RunTimeline],
    evaluators: list[str],
) -> go.Figure:
    """Build the overlay timeline figure (per-evaluator lanes, per-run colours, dots + lines).

    ``reports`` and ``timelines`` are keyed by the same short run identifier.
    ``evaluators`` is the ordered list of evaluator names to render as lanes.
    """
    run_keys = list(reports.keys())
    if not evaluators:
        return _empty_figure(message="No evaluators selected (or none have per-round evidence).")

    run_plot_data = [
        _build_run_plot_data(run_key=key, report=reports[key], timeline=timelines[key])
        for key in run_keys
    ]
    max_round = max((r.total_rounds for r in run_plot_data), default=1)
    run_colors = _build_run_colors(runs=run_plot_data)

    fig = go.Figure()
    for index, run in enumerate(run_plot_data):
        _add_run_trace(
            fig=fig,
            run=run,
            evaluators=evaluators,
            run_index=index,
            run_count=len(run_plot_data),
            colour=run_colors[run.run_key],
        )

    events_lane_y = -1.2
    _add_world_glyphs(
        fig=fig, runs=run_plot_data, events_lane_y=events_lane_y, run_colors=run_colors
    )
    _add_prominent_events(fig=fig, runs=run_plot_data, run_colors=run_colors)

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
        dragmode=False,
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


def _empty_figure(message: str) -> go.Figure:
    """Placeholder figure used when there is nothing to plot."""
    fig = go.Figure()
    fig.update_layout(
        annotations=[
            dict(text=message, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper"),
        ]
    )
    return fig
