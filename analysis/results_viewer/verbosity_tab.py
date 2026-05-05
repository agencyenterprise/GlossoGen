"""Streamlit tab plotting language-metric verbosity vs round-success rate.

One scatter point per evaluated baseline or resume run. The user picks one of
four language metrics for the X axis (MCR / MML / MWL / perplexity); Y is the
run's round-success fraction. Points are coloured by series
``(model, postmortem_enabled, baseline-vs-resume)`` so users can read whether
the verbosity → success relationship holds within each configuration.

Resume runs render as open circles to distinguish them from baseline runs;
they use ``round_success_after_resume`` so the success score is on the same
scope as the verbosity metrics (post-resume only).
"""

import json
import math

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.series_plot import (
    add_mean_trace,
    add_replica_trace,
    aggregate_buckets,
    jittered_x_linear,
    render_horizontal_checkboxes,
    series_color_map,
)
from analysis.results_viewer.verbosity_data import (
    VERBOSITY_METRIC_OPTIONS,
    VerbosityMetricOption,
    VerbosityRun,
    list_verbosity_runs,
)


def _render_frontend_base() -> str:
    """Text input for the frontend base URL used to build per-run links."""
    raw = st.text_input(
        label="Frontend base URL (for run links)",
        value="http://localhost:3000",
        key="verbosity_frontend_base",
        help="Run-id dots in the chart link to "
        "`<base>/runs/<scenario>/<run_dir_name>` on this host.",
    )
    return raw.rstrip("/")


def _run_url(frontend_base: str, run_id: str) -> str:
    """Build the per-run frontend URL."""
    return f"{frontend_base}/runs/{run_id}"


def _render_metric_selector() -> VerbosityMetricOption:
    """Radio selector + info popover letting the user pick the X-axis metric."""
    radio_col, info_col = st.columns([8, 1])
    with radio_col:
        display_names = [opt.display_name for opt in VERBOSITY_METRIC_OPTIONS]
        chosen = st.radio(
            label="X-axis metric",
            options=display_names,
            index=0,
            horizontal=True,
            key="verbosity_metric_selector",
        )
    selected = VERBOSITY_METRIC_OPTIONS[0]
    for option in VERBOSITY_METRIC_OPTIONS:
        if option.display_name == chosen:
            selected = option
            break
    with info_col:
        st.markdown("&nbsp;")
        with st.popover("ⓘ", help="How this metric is computed"):
            st.markdown(selected.description)
    return selected


_COMBINED_SERIES_KEY = "all runs"


def _render_model_filter(runs: list[VerbosityRun]) -> set[str]:
    """Checkboxes for each distinct model in the data."""
    counts: dict[str, int] = {}
    for run in runs:
        counts[run.model] = counts.get(run.model, 0) + 1
    options = [(model, model, counts[model]) for model in sorted(counts)]
    return render_horizontal_checkboxes(
        title="Model",
        options=options,
        key_prefix="verbosity_model_filter",
    )


def _render_postmortem_filter(runs: list[VerbosityRun]) -> set[bool]:
    """Two checkboxes: with-postmortem / without-postmortem."""
    counts = {True: 0, False: 0}
    for run in runs:
        counts[run.postmortem_enabled] += 1
    options = [
        ("postmortem", "with postmortem", counts[True]),
        ("no_postmortem", "no postmortem", counts[False]),
    ]
    options = [(k, lbl, c) for k, lbl, c in options if c > 0]
    selected_keys = render_horizontal_checkboxes(
        title="Postmortem",
        options=options,
        key_prefix="verbosity_postmortem_filter",
    )
    selected: set[bool] = set()
    if "postmortem" in selected_keys:
        selected.add(True)
    if "no_postmortem" in selected_keys:
        selected.add(False)
    return selected


def _render_kind_filter(runs: list[VerbosityRun]) -> set[str]:
    """Two checkboxes: baseline / resume run kinds."""
    counts = {"baseline": 0, "resume": 0}
    for run in runs:
        counts["resume" if run.is_resume else "baseline"] += 1
    options = [(k, k, counts[k]) for k in ("baseline", "resume") if counts[k] > 0]
    return render_horizontal_checkboxes(
        title="Run kind",
        options=options,
        key_prefix="verbosity_kind_filter",
    )


def _render_budget_filter(runs: list[VerbosityRun]) -> set[int | None]:
    """Checkboxes for each distinct budget bucket; ``None`` is shown as ``unknown``."""
    counts: dict[int | None, int] = {}
    for run in runs:
        counts[run.budget] = counts.get(run.budget, 0) + 1
    if not counts:
        return set()
    sorted_keys = sorted(
        counts.keys(),
        key=lambda b: (b is None, b if b is not None else 0),
    )
    options = [
        (
            "unknown" if b is None else str(b),
            "unknown" if b is None else str(b),
            counts[b],
        )
        for b in sorted_keys
    ]
    selected_keys = render_horizontal_checkboxes(
        title="Budget per round",
        options=options,
        key_prefix="verbosity_budget_filter",
    )
    selected: set[int | None] = set()
    for key in selected_keys:
        if key == "unknown":
            selected.add(None)
        else:
            selected.add(int(key))
    return selected


def _ols_line(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    """Return ``(slope, intercept)`` from a simple OLS fit, or ``None`` if undefined."""
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0:
        return None
    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = cov_xy / var_x
    intercept = mean_y - slope * mean_x
    return slope, intercept


def _build_scatter(
    runs: list[VerbosityRun],
    metric: VerbosityMetricOption,
    colour_by_series: dict[str, str],
    frontend_base: str,
) -> go.Figure:
    """Small multiples by budget: one subplot per budget bucket showing verbosity vs success.

    Each panel renders a per-run scatter coloured by series and a single OLS
    trendline fit across all selected runs in that budget. The subplot title
    carries the run count and Pearson correlation so the within-budget signal
    is readable at a glance even when the global scatter looks confounded.
    """
    by_budget: dict[int | None, list[VerbosityRun]] = {}
    for run in runs:
        if getattr(run, metric.attr) is None:
            continue
        by_budget.setdefault(run.budget, []).append(run)
    budget_keys = sorted(
        by_budget.keys(),
        key=lambda b: (b is None, b if b is not None else 0),
    )
    n_panels = max(len(budget_keys), 1)
    cols = min(n_panels, 3)
    rows = math.ceil(n_panels / cols)
    titles: list[str] = []
    for budget in budget_keys:
        bucket = by_budget[budget]
        xs = [float(getattr(r, metric.attr)) for r in bucket]
        ys = [float(r.success_fraction) for r in bucket]
        pearson = _pearson(xs=xs, ys=ys)
        pearson_text = "n/a" if pearson is None else f"r={pearson:.2f}"
        budget_label = "unknown" if budget is None else str(budget)
        titles.append(f"budget={budget_label} · n={len(bucket)} · {pearson_text}")
    fig = make_subplots(
        rows=rows,
        cols=cols,
        subplot_titles=titles,
        horizontal_spacing=0.07,
        vertical_spacing=0.18,
    )

    # Compute the global X range so each panel uses identical limits even when
    # the bucket itself spans a smaller subrange.
    all_x_values = [
        float(getattr(r, metric.attr)) for r in runs if getattr(r, metric.attr) is not None
    ]
    if all_x_values:
        x_lo, x_hi = min(all_x_values), max(all_x_values)
        x_pad = max((x_hi - x_lo) * 0.05, 1.0)
        global_x_range = [x_lo - x_pad, x_hi + x_pad]
    else:
        global_x_range = None

    seen_legend_series: set[str] = set()
    for index, budget in enumerate(budget_keys):
        row = (index // cols) + 1
        col = (index % cols) + 1
        bucket = by_budget[budget]
        series = _COMBINED_SERIES_KEY
        xs = [float(getattr(r, metric.attr)) for r in bucket]
        ys = [float(r.success_fraction) for r in bucket]
        hovers = [
            f"{r.run_id}<br>{metric.display_name}={getattr(r, metric.attr):.2f}"
            f"<br>success={r.success_fraction:.0%}"
            for r in bucket
        ]
        urls = [_run_url(frontend_base=frontend_base, run_id=r.run_id) for r in bucket]
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                name=series,
                legendgroup=series,
                marker=dict(
                    color=colour_by_series[series],
                    size=8,
                    symbol="circle",
                    opacity=0.7,
                    line=dict(width=1, color=colour_by_series[series]),
                ),
                hovertext=hovers,
                hoverinfo="text",
                customdata=urls,
                showlegend=series not in seen_legend_series,
            ),
            row=row,
            col=col,
        )
        seen_legend_series.add(series)

        # Single OLS trendline per panel (across all runs in the budget bucket).
        all_xs = [float(getattr(r, metric.attr)) for r in bucket]
        all_ys = [float(r.success_fraction) for r in bucket]
        fit = _ols_line(xs=all_xs, ys=all_ys)
        if fit is not None:
            slope, intercept = fit
            x_min, x_max = min(all_xs), max(all_xs)
            fig.add_trace(
                go.Scatter(
                    x=[x_min, x_max],
                    y=[slope * x_min + intercept, slope * x_max + intercept],
                    mode="lines",
                    line=dict(color="#444", width=1.5, dash="dash"),
                    hoverinfo="skip",
                    showlegend=False,
                ),
                row=row,
                col=col,
            )

        fig.update_yaxes(
            range=[-0.02, 1.02],
            tickformat=".0%",
            row=row,
            col=col,
        )
        if global_x_range is not None:
            fig.update_xaxes(range=global_x_range, row=row, col=col)
    # Title only once per axis class to avoid clutter; ticks remain on every
    # panel so each subplot is independently readable.
    fig.update_yaxes(title_text="round success", row=1, col=1)
    fig.update_xaxes(title_text=metric.x_axis_label, row=rows, col=(cols + 1) // 2)
    fig.update_layout(
        height=320 * rows + 80,
        margin=dict(t=60, b=60, l=60, r=20),
        legend=dict(orientation="h", y=-0.12 / rows),
        hovermode="closest",
    )
    return fig


def _build_per_round_figure(
    runs: list[VerbosityRun],
    metric: VerbosityMetricOption,
    colour_by_series: dict[str, str],
    frontend_base: str,
) -> go.Figure:
    """Per-round mean ± std line plus jittered replica dots for the combined run set."""
    fig = go.Figure()
    series = _COMBINED_SERIES_KEY
    colour = colour_by_series[series]
    xs: list[float] = []
    ys: list[float] = []
    hovers: list[str] = []
    urls: list[str] = []
    flat_round_values: list[tuple[str, float, float]] = []
    for index, run in enumerate(runs):
        for obs in run.per_round_by_metric.get(metric.display_name, []):
            xs.append(jittered_x_linear(base_x=float(obs.round_number), index=index))
            ys.append(obs.value)
            hovers.append(
                f"{run.run_id}<br>round={obs.round_number}<br>"
                f"{metric.display_name}={obs.value:.2f}"
            )
            urls.append(_run_url(frontend_base=frontend_base, run_id=run.run_id))
            flat_round_values.append((series, float(obs.round_number), obs.value))
    if xs:
        add_replica_trace(
            fig=fig,
            series=series,
            xs=xs,
            ys=ys,
            hover_texts=hovers,
            colour=colour,
            customdata=urls,
        )
    series_stats = aggregate_buckets(
        items=flat_round_values,
        series_of=lambda e: e[0],
        x_of=lambda e: e[1],
        value_of=lambda e: e[2],
    )
    if series_stats:
        add_mean_trace(
            fig=fig,
            series=series,
            stats=series_stats,
            metric_display_name=metric.display_name,
            colour=colour,
            dash="solid",
        )
    fig.update_layout(
        xaxis=dict(title="round number", dtick=1),
        yaxis=dict(title=metric.x_axis_label),
        height=520,
        margin=dict(t=30, b=40, l=60, r=20),
        legend=dict(orientation="h", y=-0.18),
        hovermode="closest",
    )
    return fig


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Population Pearson correlation; ``None`` when undefined (n<2 or zero variance)."""
    n = len(xs)
    if n < 2 or n != len(ys):
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return None
    return num / math.sqrt(var_x * var_y)


def _render_summary_table(
    runs: list[VerbosityRun],
    metric: VerbosityMetricOption,
) -> None:
    """Per-series row: count, mean success, mean metric, Pearson(metric, success)."""
    by_series: dict[str, list[VerbosityRun]] = {}
    for run in runs:
        by_series.setdefault(run.series_key(), []).append(run)
    rows: list[dict[str, object]] = []
    for series in sorted(by_series):
        bucket = [r for r in by_series[series] if getattr(r, metric.attr) is not None]
        if not bucket:
            continue
        xs = [float(getattr(r, metric.attr)) for r in bucket]
        ys = [float(r.success_fraction) for r in bucket]
        pearson = _pearson(xs=xs, ys=ys)
        rows.append(
            {
                "series": series,
                "n": len(bucket),
                f"mean {metric.display_name}": round(sum(xs) / len(xs), 3),
                "mean success": round(sum(ys) / len(ys), 3),
                "pearson(metric, success)": ("n/a" if pearson is None else round(pearson, 3)),
            }
        )
    if not rows:
        return
    overall_xs = [
        float(getattr(r, metric.attr)) for r in runs if getattr(r, metric.attr) is not None
    ]
    overall_ys = [float(r.success_fraction) for r in runs if getattr(r, metric.attr) is not None]
    overall_pearson = _pearson(xs=overall_xs, ys=overall_ys)
    rows.append(
        {
            "series": "ALL",
            "n": len(overall_xs),
            f"mean {metric.display_name}": (
                round(sum(overall_xs) / len(overall_xs), 3) if overall_xs else 0.0
            ),
            "mean success": (round(sum(overall_ys) / len(overall_ys), 3) if overall_ys else 0.0),
            "pearson(metric, success)": (
                "n/a" if overall_pearson is None else round(overall_pearson, 3)
            ),
        }
    )
    st.markdown("### Summary")
    st.dataframe(rows, width="stretch", hide_index=True)


def _maybe_open_clicked_run(chart_event: object) -> None:
    """Open the most recently clicked point in a new browser tab.

    De-duplicates via ``st.session_state["verbosity_last_opened_url"]`` so
    unrelated reruns don't re-trigger the navigation.
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
    last_key = "verbosity_last_opened_url"
    if st.session_state.get(last_key) == url:
        return
    st.session_state[last_key] = url
    encoded = json.dumps(url)
    components.html(
        f"<script>window.open({encoded}, '_blank', 'noopener,noreferrer');</script>",
        height=0,
    )
    st.toast(f"opened {url}", icon="↗")


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Verbosity tab body."""
    all_runs = list_verbosity_runs(evaluated_runs=evaluated)
    if not all_runs:
        st.info(
            "No baseline or resume runs evaluated yet. Add the 'baseline' or "
            "'resume' label and run `schmidt evaluate` with the language metrics."
        )
        return
    metric = _render_metric_selector()
    frontend_base = _render_frontend_base()
    selected_models = _render_model_filter(runs=all_runs)
    selected_postmortem = _render_postmortem_filter(runs=all_runs)
    selected_kinds = _render_kind_filter(runs=all_runs)
    selected_budgets = _render_budget_filter(runs=all_runs)
    if not selected_models:
        st.info("Select at least one model.")
        return
    if not selected_postmortem:
        st.info("Select at least one postmortem option.")
        return
    if not selected_kinds:
        st.info("Select at least one run kind.")
        return
    if not selected_budgets:
        st.info("Select at least one budget bucket.")
        return
    filtered = [
        run
        for run in all_runs
        if run.model in selected_models
        and run.postmortem_enabled in selected_postmortem
        and ("resume" if run.is_resume else "baseline") in selected_kinds
        and run.budget in selected_budgets
    ]
    metric_runs = [run for run in filtered if getattr(run, metric.attr) is not None]
    if not metric_runs:
        st.info(
            f"No selected runs have a value for `{metric.display_name}`. "
            f"Run `schmidt evaluate <scenario> --metrics {metric.display_name} ...` first."
        )
        return
    colour_by_series = series_color_map(series_keys=[_COMBINED_SERIES_KEY])
    st.markdown("### Verbosity vs round-success rate")
    fig = _build_scatter(
        runs=metric_runs,
        metric=metric,
        colour_by_series=colour_by_series,
        frontend_base=frontend_base,
    )
    chart_event = st.plotly_chart(
        fig,
        width="stretch",
        key="verbosity_chart",
        on_select="rerun",
        selection_mode=("points",),
    )
    _maybe_open_clicked_run(chart_event=chart_event)
    _render_summary_table(runs=metric_runs, metric=metric)
    st.markdown("### Per-round verbosity")
    st.caption(
        "Mean line with std error bars across all selected runs; "
        "individual replicas overlaid as faint dots so the spread is visible."
    )
    per_round_fig = _build_per_round_figure(
        runs=metric_runs,
        metric=metric,
        colour_by_series=colour_by_series,
        frontend_base=frontend_base,
    )
    per_round_event = st.plotly_chart(
        per_round_fig,
        width="stretch",
        key="verbosity_per_round_chart",
        on_select="rerun",
        selection_mode=("points",),
    )
    _maybe_open_clicked_run(chart_event=per_round_event)
