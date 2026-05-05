"""Plot helpers shared by ``baseline_tab`` and ``resume_tab``.

Both tabs render one Plotly trace per "series" (e.g. model+variant) along an
X axis (budget for baseline, round_start for resume). Each trace overlays
jittered replica dots with a mean line + std error bars. The helpers in this
module own that rendering so both tabs render identically.
"""

from typing import Callable, NamedTuple, Sequence, TypeVar

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.timeline_plot import palette_color_for_index

_RunT = TypeVar("_RunT")


CORE_LABEL_PREFIXES: tuple[str, ...] = (
    "baseline",
    "budget=",
    "eval:",
    "postmortem=",
    "single_team",
    "two_team",
)
"""Label prefixes treated as standard run metadata; everything else is opt-in batch tag."""


class SeriesStats(NamedTuple):
    """Aggregate statistics for one (series, x) bucket."""

    series: str
    x_value: float
    n: int
    mean: float
    std: float
    min_value: float
    max_value: float


def series_color_map(series_keys: list[str]) -> dict[str, str]:
    """Assign a palette colour to each series, stable across reruns."""
    return {key: palette_color_for_index(index=i) for i, key in enumerate(series_keys)}


def add_replica_trace(
    fig: go.Figure,
    series: str,
    xs: list[float],
    ys: list[float],
    hover_texts: list[str],
    colour: str,
    customdata: list[str] | None,
) -> None:
    """Scatter individual replicas with light X-jitter so overlapping points resolve.

    Caller computes both the x value and the metric value per replica because
    different tabs use different x axes (log-scale budget vs linear round_start).

    ``customdata`` attaches a per-point string (e.g. a URL) that the caller can
    read back from Streamlit selection events; pass ``None`` when the trace
    does not need point-level metadata.
    """
    trace_kwargs: dict[str, object] = dict(
        x=xs,
        y=ys,
        mode="markers",
        name=f"{series} · replicas",
        marker=dict(color=colour, size=7, opacity=0.35),
        hovertext=hover_texts,
        hoverinfo="text",
        showlegend=False,
    )
    if customdata is not None:
        trace_kwargs["customdata"] = customdata
    fig.add_trace(go.Scatter(**trace_kwargs))


def add_mean_trace(
    fig: go.Figure,
    series: str,
    stats: list[SeriesStats],
    metric_display_name: str,
    colour: str,
    dash: str,
) -> None:
    """Mean line with std error bars for a single series."""
    stats_sorted = sorted(stats, key=lambda s: s.x_value)
    fig.add_trace(
        go.Scatter(
            x=[s.x_value for s in stats_sorted],
            y=[s.mean for s in stats_sorted],
            error_y=dict(
                type="data",
                array=[s.std for s in stats_sorted],
                visible=True,
                thickness=1.5,
                width=6,
                color=colour,
            ),
            mode="lines+markers",
            name=series,
            line=dict(color=colour, width=2.5, dash=dash),
            marker=dict(color=colour, size=10, symbol="circle"),
            hovertemplate=(
                f"series=%{{text}}<br>x=%{{x}}<br>{metric_display_name} "
                "mean=%{y:g}<extra></extra>"
            ),
            text=[series] * len(stats_sorted),
        )
    )


def jittered_x(base_x: float, index: int) -> float:
    """Return ``base_x`` with a small deterministic horizontal offset for replica scatter."""
    return base_x * (1.0 + ((index % 5) - 2) * 0.01)


def jittered_x_linear(base_x: float, index: int) -> float:
    """Linear-scale jitter that adds a small absolute offset rather than a multiplicative one.

    Use when the X axis is linear and ``base_x`` may be 0; the multiplicative
    form collapses on zero and is misleading when values are small integers.
    """
    return base_x + ((index % 5) - 2) * 0.05


def aggregate_buckets(
    items: Sequence[_RunT],
    series_of: Callable[[_RunT], str],
    x_of: Callable[[_RunT], float],
    value_of: Callable[[_RunT], float],
) -> list[SeriesStats]:
    """Group ``items`` by ``(series, x)`` and emit per-bucket aggregate statistics.

    Output is sorted by series then x so plot traces render in a stable order.
    """
    buckets: dict[tuple[str, float], list[float]] = {}
    for item in items:
        key = (series_of(item), x_of(item))
        if key not in buckets:
            buckets[key] = []
        buckets[key].append(value_of(item))
    out: list[SeriesStats] = []
    for (series, x_value), values in sorted(buckets.items()):
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = float(variance**0.5)
        out.append(
            SeriesStats(
                series=series,
                x_value=x_value,
                n=len(values),
                mean=mean,
                std=std,
                min_value=min(values),
                max_value=max(values),
            )
        )
    return out


def render_horizontal_checkboxes(
    title: str,
    options: list[tuple[str, str, int]],
    key_prefix: str,
) -> set[str]:
    """Render a horizontal row of checkboxes; return the selected option keys.

    ``options`` is a list of ``(option_key, label, count)`` tuples. The label
    is what the user sees; the option_key is what's returned. Counts are
    appended to the label in parentheses.
    """
    if not options:
        return set()
    st.markdown(f"**{title}**")
    cols = st.columns(len(options))
    selected: set[str] = set()
    for col, (key, label, count) in zip(cols, options):
        if col.checkbox(
            label=f"{label} ({count})",
            value=True,
            key=f"{key_prefix}::{key}",
        ):
            selected.add(key)
    return selected


def batch_label_filter(
    runs: Sequence[_RunT],
    labels_of: Callable[[_RunT], list[str]],
    excluded_label_values: frozenset[str],
    streamlit_key_prefix: str,
) -> tuple[list[_RunT], frozenset[str]]:
    """Render checkboxes for non-core batch labels and return runs matching all selected ones.

    ``excluded_label_values`` lists labels that appear on the runs but are
    metadata (e.g. the model name) rather than batch tags. They are filtered
    out before the checkbox stack is rendered.
    """
    batch_labels: set[str] = set()
    for run in runs:
        for label in labels_of(run):
            if any(label.startswith(prefix) for prefix in CORE_LABEL_PREFIXES):
                continue
            if label in excluded_label_values:
                continue
            batch_labels.add(label)
    if not batch_labels:
        return list(runs), frozenset()
    st.markdown("**Batch labels**")
    selected: set[str] = set()
    for label in sorted(batch_labels):
        count = sum(1 for r in runs if label in labels_of(r))
        if st.checkbox(
            label=f"{label} ({count})",
            value=True,
            key=f"{streamlit_key_prefix}::{label}",
        ):
            selected.add(label)
    unselected = batch_labels - selected
    filtered = [r for r in runs if not any(label in labels_of(r) for label in unselected)]
    return filtered, frozenset(selected)
