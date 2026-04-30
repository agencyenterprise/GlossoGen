"""Streamlit tab rendering the baseline sweep: budget vs a user-chosen metric per series.

A series is one (model, postmortem_enabled) variant — each gets its own line and
colour, so e.g. sonnet-4.6 with postmortem and sonnet-4.6 without postmortem
render as two distinct traces. The user picks which metric is on the Y axis
(``round_success`` / ``round_ended_idle`` / ``round_ended_timeout`` /
``content_filter_refusal`` / ``perplexity``); the same chart adapts its Y range
and tick spacing to the selected metric. Clicking a replica dot opens the
corresponding run in the schmidt frontend (URL is attached to each point as
``customdata`` and read back from the chart's selection event).
"""

import json

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from analysis.results_viewer.baseline_data import (
    METRIC_OPTIONS,
    BaselineRun,
    BudgetStats,
    MetricOption,
    YAxisSpec,
    aggregate_by_budget,
    list_baseline_runs,
)
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.series_plot import (
    SeriesStats,
    add_mean_trace,
    add_replica_trace,
    batch_label_filter,
    jittered_x,
    series_color_map,
)


def _render_frontend_base() -> str:
    """Text input for the frontend base URL used to build per-run links.

    Returned value is trimmed of trailing slashes. Defaults to the local dev
    server; the user can paste a Railway / production URL to deep-link into a
    deployed frontend instead.
    """
    raw = st.text_input(
        label="Frontend base URL (for run links)",
        value="http://localhost:3000",
        key="baseline_frontend_base",
        help="Run-id dots in the chart and the table below link to "
        "`<base>/runs/<scenario>/<run_dir_name>` on this host.",
    )
    return raw.rstrip("/")


def _run_url(frontend_base: str, run_id: str) -> str:
    """Build the per-run frontend URL: ``<base>/runs/<scenario>/<run_dir_name>``.

    ``run_id`` already has the ``<scenario>/<run_dir_name>`` shape from
    ``run_catalog._derive_run_id``, so the final path is just ``/runs/<run_id>``.
    """
    return f"{frontend_base}/runs/{run_id}"


def _render_metric_selector() -> MetricOption:
    """Radio selector + info popover letting the user pick the Y-axis metric.

    Renders the radio and a small ``ⓘ`` popover side-by-side; the popover's
    contents describe how the currently selected metric is computed.
    """
    radio_col, info_col = st.columns([8, 1])
    with radio_col:
        display_names = [opt.display_name for opt in METRIC_OPTIONS]
        chosen = st.radio(
            label="Metric",
            options=display_names,
            index=0,
            horizontal=True,
            key="baseline_metric_selector",
        )
    selected = METRIC_OPTIONS[0]
    for option in METRIC_OPTIONS:
        if option.display_name == chosen:
            selected = option
            break
    with info_col:
        st.markdown("&nbsp;")
        with st.popover("ⓘ", help="How this metric is computed"):
            st.markdown(selected.description)
    return selected


def _series_checkbox_filter(
    runs: list[BaselineRun], selected_batch_labels: frozenset[str]
) -> set[str]:
    """Render one checkbox per distinct series; return the set of selected series keys."""
    counts: dict[str, int] = {}
    for run in runs:
        key = run.series_key(selected_batch_labels=selected_batch_labels)
        counts[key] = counts.get(key, 0) + 1
    st.markdown("**Series (model · postmortem variant)**")
    selected: set[str] = set()
    for name in sorted(counts):
        if st.checkbox(
            label=f"{name} ({counts[name]})",
            value=True,
            key=f"baseline_series_filter::{name}",
        ):
            selected.add(name)
    return selected


def _replica_xs_ys_hover(
    runs: list[BaselineRun],
    series: str,
    metric: MetricOption,
    frontend_base: str,
) -> tuple[list[float], list[float], list[str], list[str]]:
    """Compute jittered X, Y, hover text, and per-point URLs for ``add_replica_trace``.

    The URL is also stamped into the hover and into ``customdata`` so the
    ``render`` function can read it back from the Streamlit selection event
    and open the run in a new tab when the user clicks a dot.
    """
    xs: list[float] = []
    ys: list[float] = []
    hover: list[str] = []
    urls: list[str] = []
    for index, run in enumerate(runs):
        value = metric.extract(run=run)
        url = _run_url(frontend_base=frontend_base, run_id=run.run_id)
        xs.append(jittered_x(base_x=run.budget, index=index))
        ys.append(value)
        hover.append(
            f"{run.run_id}<br>{series}<br>budget={run.budget}<br>"
            f"{metric.display_name}={value:g}<br>"
            f"click to open · {url}"
        )
        urls.append(url)
    return xs, ys, hover, urls


def _budget_stats_to_series_stats(stats: list[BudgetStats]) -> list[SeriesStats]:
    """Convert ``BudgetStats`` rows into the shared ``SeriesStats`` shape."""
    return [
        SeriesStats(
            series=s.series,
            x_value=float(s.budget),
            n=s.n,
            mean=s.mean,
            std=s.std,
            min_value=s.min_value,
            max_value=s.max_value,
        )
        for s in stats
    ]


def _build_figure(
    runs: list[BaselineRun],
    stats: list[BudgetStats],
    colour_by_series: dict[str, str],
    metric: MetricOption,
    selected_batch_labels: frozenset[str],
    y_axis: YAxisSpec,
    x_tickvals: list[int],
    frontend_base: str,
) -> go.Figure:
    """Assemble the budget → metric figure with mean ± std and replica dots.

    ``y_axis`` and ``x_tickvals`` are passed in so the axes stay fixed when
    the user toggles series/batch filters; recomputing them from ``runs``
    would shrink the chart whenever a series is hidden.
    """
    fig = go.Figure()
    runs_by_series: dict[str, list[BaselineRun]] = {}
    for run in runs:
        runs_by_series.setdefault(
            run.series_key(selected_batch_labels=selected_batch_labels), []
        ).append(run)
    stats_by_series: dict[str, list[BudgetStats]] = {}
    for stat in stats:
        stats_by_series.setdefault(stat.series, []).append(stat)
    for series, colour in colour_by_series.items():
        if series not in runs_by_series:
            continue
        xs, ys, hover, urls = _replica_xs_ys_hover(
            runs=runs_by_series[series],
            series=series,
            metric=metric,
            frontend_base=frontend_base,
        )
        add_replica_trace(
            fig=fig,
            series=series,
            xs=xs,
            ys=ys,
            hover_texts=hover,
            colour=colour,
            customdata=urls,
        )
        if series in stats_by_series:
            add_mean_trace(
                fig=fig,
                series=series,
                stats=_budget_stats_to_series_stats(stats=stats_by_series[series]),
                metric_display_name=metric.display_name,
                colour=colour,
                dash="solid",
            )
    yaxis_kwargs: dict[str, object] = {
        "title": f"{metric.y_axis_label} (mean ± std)",
        "range": [y_axis.y_min, y_axis.y_max],
    }
    if y_axis.dtick is not None:
        yaxis_kwargs["dtick"] = y_axis.dtick
    fig.update_layout(
        xaxis=dict(
            title="round_time_budget_seconds (log scale)",
            type="log",
            tickmode="array",
            tickvals=x_tickvals,
            ticktext=[str(b) for b in x_tickvals],
        ),
        yaxis=yaxis_kwargs,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=20, t=40, b=60),
        height=500,
    )
    return fig


def _render_stats_table(stats: list[BudgetStats], metric: MetricOption) -> None:
    """Tabular view of the per-bucket statistics below the chart."""
    rows = [
        {
            "series": s.series,
            "budget": s.budget,
            "n": s.n,
            f"{metric.display_name} mean": round(s.mean, 4),
            f"{metric.display_name} std": round(s.std, 4),
            "min": round(s.min_value, 4),
            "max": round(s.max_value, 4),
        }
        for s in sorted(stats, key=lambda s: (s.series, s.budget))
    ]
    st.markdown("### Aggregate statistics")
    st.dataframe(rows, width="stretch", hide_index=True)


def _maybe_open_clicked_run(chart_event: object) -> None:
    """Open the most recently clicked replica in a new browser tab.

    Streamlit reruns the script on every selection change, so we
    de-duplicate via ``st.session_state["baseline_last_opened_url"]`` to avoid
    re-opening the same run when the user toggles an unrelated filter. The
    actual navigation is done by injecting a tiny ``window.open`` script via
    ``components.html`` — Streamlit has no native "open external URL" call.
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
    last_key = "baseline_last_opened_url"
    if st.session_state.get(last_key) == url:
        return
    st.session_state[last_key] = url
    encoded = json.dumps(url)
    components.html(
        f"<script>window.open({encoded}, '_blank', 'noopener,noreferrer');</script>",
        height=0,
    )
    st.toast(f"opened {url}", icon="↗")


def _render_included_runs(
    runs: list[BaselineRun],
    metric: MetricOption,
    selected_batch_labels: frozenset[str],
    frontend_base: str,
) -> None:
    """Per-replica audit listing inside an expander.

    The ``url`` column is rendered as a clickable LinkColumn so users can
    open a specific replica in the schmidt frontend to investigate a high or
    low ``perplexity`` (or any other metric) outlier.
    """
    rows = [
        {
            "series": r.series_key(selected_batch_labels=selected_batch_labels),
            "budget": r.budget,
            metric.display_name: round(metric.extract(run=r), 4),
            "run_id": r.run_id,
            "url": _run_url(frontend_base=frontend_base, run_id=r.run_id),
        }
        for r in sorted(
            runs,
            key=lambda r: (
                r.series_key(selected_batch_labels=selected_batch_labels),
                r.budget,
                r.run_id,
            ),
        )
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
                    help="Open this replica in the schmidt frontend",
                ),
            },
        )


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Baseline tab body."""
    all_baseline = list_baseline_runs(evaluated_runs=evaluated)
    if not all_baseline:
        st.info(
            "No runs labeled 'baseline' found. "
            "Add the 'baseline' label to runs you want in this view."
        )
        return
    metric = _render_metric_selector()
    frontend_base = _render_frontend_base()
    excluded = frozenset(run.model for run in all_baseline)
    batch_filtered, selected_batch_labels = batch_label_filter(
        runs=all_baseline,
        labels_of=lambda run: run.labels,
        excluded_label_values=excluded,
        streamlit_key_prefix="baseline_batch_filter",
    )
    if not batch_filtered:
        st.info("Select at least one batch label.")
        return
    selected_series = _series_checkbox_filter(
        runs=batch_filtered, selected_batch_labels=selected_batch_labels
    )
    if not selected_series:
        st.info("Select at least one series.")
        return
    filtered = [
        run
        for run in batch_filtered
        if run.series_key(selected_batch_labels=selected_batch_labels) in selected_series
    ]
    if not filtered:
        st.info("No baseline runs for the selected series.")
        return
    metric_runs = [run for run in filtered if metric.available(run=run)]
    if not metric_runs:
        st.info(
            f"No selected baseline runs have a value for `{metric.display_name}`. "
            "For perplexity, run `python -m schmidt evaluate <scenario> "
            "--metrics perplexity ...` on the runs you want included."
        )
        return
    series_ordered = sorted(
        {r.series_key(selected_batch_labels=selected_batch_labels) for r in metric_runs}
    )
    colour_by_series = series_color_map(series_keys=series_ordered)
    stats = aggregate_by_budget(
        runs=metric_runs,
        value_of=metric.extract,
        selected_batch_labels=selected_batch_labels,
    )
    # Compute axis ranges from the unfiltered baseline set so the chart's
    # X tick layout and Y range stay constant when the user toggles series.
    y_axis = metric.y_axis(runs=all_baseline)
    x_tickvals = sorted({r.budget for r in all_baseline})
    fig = _build_figure(
        runs=metric_runs,
        stats=stats,
        colour_by_series=colour_by_series,
        metric=metric,
        selected_batch_labels=selected_batch_labels,
        y_axis=y_axis,
        x_tickvals=x_tickvals,
        frontend_base=frontend_base,
    )
    chart_event = st.plotly_chart(
        fig,
        width="stretch",
        key="baseline_chart",
        on_select="rerun",
        selection_mode=("points",),
    )
    _maybe_open_clicked_run(chart_event=chart_event)
    _render_stats_table(stats=stats, metric=metric)
    _render_included_runs(
        runs=metric_runs,
        metric=metric,
        selected_batch_labels=selected_batch_labels,
        frontend_base=frontend_base,
    )
