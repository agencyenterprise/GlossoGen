"""Builds the Plotly timeline figure overlaying multiple runs' per-round hits."""

from typing import NamedTuple

import plotly.graph_objects as go
from plotly.subplots import make_subplots

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


def _is_value_metric(reports: list[EvaluationReport], metric_name: str) -> bool:
    """A metric is a *value* metric if any per_round entry has value != 1.0.

    Flag metrics (neologism, round_ended_idle, etc.) only ever emit
    ``value=1.0`` for rounds where the phenomenon fired. Value metrics
    (perplexity, mcr, round_success) emit varying numbers per round —
    plotting them as binary lane dots loses information.
    """
    for report in reports:
        for measurement in report.measurements:
            if measurement.metric_name != metric_name:
                continue
            for obs in measurement.per_round:
                if obs.value != 1.0:
                    return True
    return False


def collect_flag_metrics(reports: list[EvaluationReport]) -> list[str]:
    """Metric names that are flag-style (binary fire/no-fire per round).

    Used by the lane plot. Value metrics like perplexity and mcr are excluded
    because every round fires and a binary lane carries no signal.
    """
    names: set[str] = set()
    for report in reports:
        for measurement in report.measurements:
            if not measurement.per_round:
                continue
            if _is_value_metric(reports=reports, metric_name=measurement.metric_name):
                continue
            if any(obs.value > 0 for obs in measurement.per_round):
                names.add(measurement.metric_name)
    return sorted(names)


def collect_value_metrics(reports: list[EvaluationReport]) -> list[str]:
    """Metric names that carry a meaningful per-round numeric value.

    Used by the per-round value subplot grid (perplexity nats, mcr
    chars/round, round_success 0/1, etc.).
    """
    names: set[str] = set()
    for report in reports:
        for measurement in report.measurements:
            if not measurement.per_round:
                continue
            if _is_value_metric(reports=reports, metric_name=measurement.metric_name):
                names.add(measurement.metric_name)
    return sorted(names)


def _build_run_plot_data(
    run_key: str,
    report: EvaluationReport,
    timeline: RunTimeline,
) -> _RunPlotData:
    """Build the per-metric rounds mapping for one run."""
    per_metric: dict[str, list[int]] = {}
    for measurement in report.measurements:
        flagged = sorted(obs.round_number for obs in measurement.per_round if obs.value > 0)
        if flagged:
            per_metric[measurement.metric_name] = flagged
    return _RunPlotData(
        run_key=run_key,
        total_rounds=timeline.total_rounds,
        per_evaluator_rounds=per_metric,
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
    metrics: list[str],
    run_index: int,
    run_count: int,
    colour: str,
) -> None:
    """Add one dots+lines trace per (run, metric lane); legend shows the run once.

    Each visible dot carries ``customdata = [run_key, metric_name, round]``. Transparent
    intermediate markers are added along the connecting line so clicks on the line segment
    also open the modal (mapped to the nearest real round).
    """
    offset = _run_vertical_offset(run_index=run_index, run_count=run_count)
    legend_shown = False
    for eval_name in metrics:
        rounds = run.per_evaluator_rounds.get(eval_name)
        if not rounds:
            continue
        base_y = metrics.index(eval_name)
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
    metrics: list[str],
) -> go.Figure:
    """Build the overlay timeline figure (per-metric lanes, per-run colours, dots + lines).

    ``reports`` and ``timelines`` are keyed by the same short run identifier.
    ``metrics`` is the ordered list of metric names to render as lanes.
    """
    run_keys = list(reports.keys())
    if not metrics:
        return _empty_figure(message="No metrics selected (or none have per-round entries).")

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
            metrics=metrics,
            run_index=index,
            run_count=len(run_plot_data),
            colour=run_colors[run.run_key],
        )

    events_lane_y = -1.2
    _add_world_glyphs(
        fig=fig, runs=run_plot_data, events_lane_y=events_lane_y, run_colors=run_colors
    )
    _add_prominent_events(fig=fig, runs=run_plot_data, run_colors=run_colors)

    tickvals = [events_lane_y, *range(len(metrics))]
    ticktext = [_EVENTS_LANE_LABEL, *metrics]

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
            range=[events_lane_y - 0.6, len(metrics) - 0.4],
            showgrid=True,
            gridcolor="rgba(0,0,0,0.04)",
        ),
        height=220 + 90 * len(metrics),
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


def _measurement_score_unit(reports: list[EvaluationReport], metric_name: str) -> str:
    """Pick the first non-empty score_unit string for ``metric_name`` across reports."""
    for report in reports:
        for measurement in report.measurements:
            if measurement.metric_name == metric_name and measurement.score_unit:
                return measurement.score_unit
    return ""


def _per_round_for_metric(
    report: EvaluationReport, metric_name: str
) -> tuple[list[int], list[float]]:
    """Return parallel lists of round numbers and values for ``metric_name`` in ``report``."""
    for measurement in report.measurements:
        if measurement.metric_name != metric_name:
            continue
        sorted_obs = sorted(measurement.per_round, key=lambda obs: obs.round_number)
        rounds = [obs.round_number for obs in sorted_obs]
        values = [obs.value for obs in sorted_obs]
        return rounds, values
    return [], []


_METRIC_DASH_PATTERNS = ["solid", "dash", "dot", "dashdot", "longdash", "longdashdot"]


class _SplitMetrics(NamedTuple):
    """Split value metrics into continuous (shared Y axis) and binary success (rug strip)."""

    continuous: list[str]
    success: list[str]


def _split_value_metrics(metrics: list[str]) -> _SplitMetrics:
    """Pull ``round_success*`` out of the metric list — those render as a rug strip."""
    continuous = [name for name in metrics if not name.startswith("round_success")]
    success = [name for name in metrics if name.startswith("round_success")]
    return _SplitMetrics(continuous=continuous, success=success)


def _add_continuous_value_traces(
    fig: go.Figure,
    row: int,
    reports: dict[str, EvaluationReport],
    metrics: list[str],
    run_keys: list[str],
    run_colors: dict[str, str],
    metric_dash: dict[str, str],
) -> None:
    """Lines for every (run, metric) on the shared Y axis; legend proxies handle naming."""
    for metric_name in metrics:
        for run_key in run_keys:
            rounds, values = _per_round_for_metric(report=reports[run_key], metric_name=metric_name)
            if not rounds:
                continue
            fig.add_trace(
                go.Scatter(
                    x=rounds,
                    y=values,
                    mode="markers+lines",
                    name=f"{run_key} · {metric_name}",
                    legendgroup=f"run::{run_key}",
                    showlegend=False,
                    line=dict(color=run_colors[run_key], width=2, dash=metric_dash[metric_name]),
                    marker=dict(color=run_colors[run_key], size=7),
                    hovertemplate=(
                        f"<b>{run_key}</b><br>round %{{x}}<br>{metric_name}: %{{y:.3f}}"
                        "<extra></extra>"
                    ),
                ),
                row=row,
                col=1,
            )


def _add_legend_proxies(
    fig: go.Figure,
    row: int,
    run_keys: list[str],
    run_colors: dict[str, str],
    metrics: list[str],
    metric_dash: dict[str, str],
    metric_label: dict[str, str],
) -> None:
    """Invisible traces that populate two legend groups: runs (colour) and metrics (dash)."""
    for run_key in run_keys:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="lines",
                line=dict(color=run_colors[run_key], width=3),
                name=run_key,
                legendgroup="runs",
                legendgrouptitle=dict(text="Runs"),
                showlegend=True,
            ),
            row=row,
            col=1,
        )
    for metric_name in metrics:
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="lines",
                line=dict(color="rgba(80,80,80,0.85)", width=3, dash=metric_dash[metric_name]),
                name=metric_label[metric_name],
                legendgroup="metrics",
                legendgrouptitle=dict(text="Metrics (line style)"),
                showlegend=True,
            ),
            row=row,
            col=1,
        )


def _add_success_rug(
    fig: go.Figure,
    row: int,
    reports: dict[str, EvaluationReport],
    metrics: list[str],
    run_keys: list[str],
    run_colors: dict[str, str],
) -> None:
    """One row per round_success metric; vertical ticks per run on rounds where value > 0."""
    run_count = len(run_keys)
    for metric_index, metric_name in enumerate(metrics):
        for run_index, run_key in enumerate(run_keys):
            rounds, values = _per_round_for_metric(report=reports[run_key], metric_name=metric_name)
            success_rounds = [r for r, v in zip(rounds, values) if v > 0]
            if not success_rounds:
                continue
            offset = _run_vertical_offset(run_index=run_index, run_count=run_count)
            y_pos = metric_index + offset
            fig.add_trace(
                go.Scatter(
                    x=success_rounds,
                    y=[y_pos] * len(success_rounds),
                    mode="markers",
                    marker=dict(
                        color=run_colors[run_key],
                        symbol="line-ns",
                        size=18,
                        line=dict(width=3, color=run_colors[run_key]),
                    ),
                    name=f"{run_key} · {metric_name}",
                    legendgroup=f"run::{run_key}",
                    showlegend=False,
                    hovertemplate=(
                        f"<b>{run_key}</b><br>{metric_name}<br>round %{{x}} succeeded"
                        "<extra></extra>"
                    ),
                ),
                row=row,
                col=1,
            )


def _shared_y_axis_title(reports: list[EvaluationReport], metrics: list[str]) -> str:
    """Join the distinct units of the continuous metrics for the shared Y axis label."""
    units = []
    seen: set[str] = set()
    for name in metrics:
        unit = _measurement_score_unit(reports=reports, metric_name=name)
        if unit and unit not in seen:
            seen.add(unit)
            units.append(unit)
    if not units:
        return "value"
    return " / ".join(units)


def build_value_metrics_figure(
    reports: dict[str, EvaluationReport],
    metrics: list[str],
) -> go.Figure:
    """Continuous metrics share one Y axis; ``round_success*`` metrics render as a rug strip below.

    Continuous metrics (perplexity, mcr, …) are drawn as lines on a single
    shared subplot — colour distinguishes runs, line dash distinguishes metrics.
    Binary ``round_success*`` metrics get their own narrow row underneath, with
    one vertical tick per (run, succeeded round).
    """
    if not metrics:
        return _empty_figure(message="No value metrics selected.")

    split = _split_value_metrics(metrics=metrics)
    run_keys = list(reports.keys())
    report_list = list(reports.values())
    run_colors = {key: _RUN_PALETTE[i % len(_RUN_PALETTE)] for i, key in enumerate(run_keys)}

    has_continuous = bool(split.continuous)
    has_success = bool(split.success)

    metric_dash = {
        name: _METRIC_DASH_PATTERNS[i % len(_METRIC_DASH_PATTERNS)]
        for i, name in enumerate(split.continuous)
    }
    metric_label = {
        name: (
            f"{name} ({_measurement_score_unit(reports=report_list, metric_name=name)})"
            if _measurement_score_unit(reports=report_list, metric_name=name)
            else name
        )
        for name in split.continuous
    }

    continuous_row = 1
    success_row = 1
    if has_continuous and has_success:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            row_heights=[0.78, 0.22],
            subplot_titles=["Per-round values", "Round success"],
        )
        success_row = 2
    elif has_continuous:
        fig = make_subplots(rows=1, cols=1, subplot_titles=["Per-round values"])
    else:
        fig = make_subplots(rows=1, cols=1, subplot_titles=["Round success"])

    if has_continuous:
        _add_continuous_value_traces(
            fig=fig,
            row=continuous_row,
            reports=reports,
            metrics=split.continuous,
            run_keys=run_keys,
            run_colors=run_colors,
            metric_dash=metric_dash,
        )
        _add_legend_proxies(
            fig=fig,
            row=continuous_row,
            run_keys=run_keys,
            run_colors=run_colors,
            metrics=split.continuous,
            metric_dash=metric_dash,
            metric_label=metric_label,
        )
        fig.update_yaxes(
            title_text=_shared_y_axis_title(reports=report_list, metrics=split.continuous),
            row=continuous_row,
            col=1,
        )

    if has_success:
        _add_success_rug(
            fig=fig,
            row=success_row,
            reports=reports,
            metrics=split.success,
            run_keys=run_keys,
            run_colors=run_colors,
        )
        fig.update_yaxes(
            tickmode="array",
            tickvals=list(range(len(split.success))),
            ticktext=split.success,
            range=[-0.6, len(split.success) - 0.4],
            row=success_row,
            col=1,
        )

    last_row = 2 if (has_continuous and has_success) else 1
    fig.update_xaxes(title_text="Round", dtick=1, row=last_row, col=1)

    height = 0
    if has_continuous:
        height += 460
    if has_success:
        height += 80 + 50 * len(split.success)

    fig.update_layout(
        height=max(height, 320),
        hovermode="closest",
        plot_bgcolor="white",
        margin=dict(l=80, r=240, t=60, b=50),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1.0,
            xanchor="left",
            x=1.02,
            groupclick="toggleitem",
        ),
    )
    return fig
