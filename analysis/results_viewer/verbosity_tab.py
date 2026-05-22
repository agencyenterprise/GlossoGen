"""Streamlit tab plotting language-metric verbosity vs round-success rate.

One scatter point per evaluated baseline or resume run. The user picks one of
three language metrics for the X axis (MCR / MCM / perplexity); Y is the
run's round-success fraction. Points are coloured by series
``(model, postmortem_enabled, baseline-vs-resume)`` so users can read whether
the verbosity → success relationship holds within each configuration.

Resume runs render as open circles to distinguish them from baseline runs;
they use ``round_success_after_resume`` so the success score is on the same
scope as the verbosity metrics (post-resume only).
"""

import math

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from analysis.results_viewer import seed_mode_filter
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import maybe_open_clicked_run, render_frontend_base, run_url
from analysis.results_viewer.series_plot import (
    add_mean_trace,
    add_replica_trace,
    aggregate_buckets,
    jittered_x_linear,
    render_horizontal_checkboxes,
    series_color_map,
)
from analysis.results_viewer.timeline_plot import palette_color_for_index
from analysis.results_viewer.verbosity_data import (
    VERBOSITY_METRIC_OPTIONS,
    VerbosityMetricOption,
    VerbosityRun,
    list_verbosity_runs,
)


def _scenarios_with_verbosity_runs(evaluated: list[EvaluatedRun]) -> list[str]:
    """Return every scenario with at least one evaluated run.

    The verbosity tab plots ``mean_chars_per_round`` / ``mean_chars_per_message``
    against ``round_success`` — both come from the generic platform
    registry, so any scenario that opts into ``get_primary_channel_id``
    qualifies. Auto-discovered from the loaded runs.
    """
    return sorted({run.scenario_name for run in evaluated})


def _render_scenario_selector(evaluated: list[EvaluatedRun]) -> str | None:
    """Radio selector listing every scenario that has evaluated runs."""
    options = _scenarios_with_verbosity_runs(evaluated=evaluated)
    if not options:
        return None
    chosen = st.radio(
        label="Scenario",
        options=options,
        index=0,
        horizontal=True,
        key="verbosity_scenario_selector",
    )
    return chosen


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
        initial_state=True,
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
        initial_state=True,
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
        initial_state=True,
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
        initial_state=True,
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
        urls = [run_url(frontend_base=frontend_base, run_id=r.run_id) for r in bucket]
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


_VERBOSITY_X_OPTIONS: list[VerbosityMetricOption] = [
    opt for opt in VERBOSITY_METRIC_OPTIONS if opt.display_name in ("mcr", "mcm")
]


def _render_verbosity_x_selector() -> VerbosityMetricOption:
    """Radio selector for the verbosity-vs-perplexity scatter X axis (MCR or MCM)."""
    display_names = [opt.display_name for opt in _VERBOSITY_X_OPTIONS]
    chosen = st.radio(
        label="Verbosity metric (X)",
        options=display_names,
        index=0,
        horizontal=True,
        key="verbosity_vs_ppl_x_selector",
    )
    selected = _VERBOSITY_X_OPTIONS[0]
    for option in _VERBOSITY_X_OPTIONS:
        if option.display_name == chosen:
            selected = option
            break
    return selected


def _budget_color_map(runs: list[VerbosityRun]) -> dict[int | None, str]:
    """Stable palette colour per distinct budget bucket present in ``runs``."""
    budgets = sorted(
        {run.budget for run in runs},
        key=lambda b: (b is None, b if b is not None else 0),
    )
    return {budget: palette_color_for_index(index=i) for i, budget in enumerate(budgets)}


def _build_verbosity_vs_perplexity_figure(
    runs: list[VerbosityRun],
    x_metric: VerbosityMetricOption,
    frontend_base: str,
) -> go.Figure | None:
    """Per-(run, round) scatter of verbosity (MCR or MCM) against perplexity.

    Joins each run's per-round verbosity values with its per-round perplexity
    values by ``round_number``. Points coloured by budget bucket; single OLS
    trendline plus Pearson correlation are computed across all displayed
    points so the inverse trend is explicit. Returns ``None`` when no
    (run, round) pair has both metrics populated.
    """
    fig = go.Figure()
    budget_colour = _budget_color_map(runs=runs)
    all_xs: list[float] = []
    all_ys: list[float] = []
    by_budget: dict[int | None, list[tuple[float, float, str, str]]] = {}
    for run in runs:
        verbosity_rounds = {
            obs.round_number: obs.value
            for obs in run.per_round_by_metric.get(x_metric.display_name, [])
        }
        perplexity_rounds = {
            obs.round_number: obs.value for obs in run.per_round_by_metric.get("perplexity", [])
        }
        shared_rounds = sorted(set(verbosity_rounds) & set(perplexity_rounds))
        if not shared_rounds:
            continue
        for round_number in shared_rounds:
            x_value = float(verbosity_rounds[round_number])
            y_value = float(perplexity_rounds[round_number])
            hover = (
                f"{run.run_id}<br>round={round_number}<br>"
                f"{x_metric.display_name}={x_value:.2f}<br>perplexity={y_value:.2f}<br>"
                f"budget={run.budget if run.budget is not None else 'unknown'}"
            )
            url = run_url(frontend_base=frontend_base, run_id=run.run_id)
            by_budget.setdefault(run.budget, []).append((x_value, y_value, hover, url))
            all_xs.append(x_value)
            all_ys.append(y_value)
    if not all_xs:
        return None
    budget_keys = sorted(
        by_budget.keys(),
        key=lambda b: (b is None, b if b is not None else 0),
    )
    for budget in budget_keys:
        points = by_budget[budget]
        budget_label = "unknown" if budget is None else str(budget)
        fig.add_trace(
            go.Scatter(
                x=[p[0] for p in points],
                y=[p[1] for p in points],
                mode="markers",
                name=f"budget={budget_label}",
                marker=dict(
                    color=budget_colour[budget],
                    size=7,
                    symbol="circle",
                    opacity=0.65,
                    line=dict(width=0.5, color="#222"),
                ),
                hovertext=[p[2] for p in points],
                hoverinfo="text",
                customdata=[p[3] for p in points],
            )
        )
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
                name="OLS fit",
                hoverinfo="skip",
                showlegend=False,
            )
        )
    pearson = _pearson(xs=all_xs, ys=all_ys)
    pearson_text = "n/a" if pearson is None else f"r={pearson:.2f}"
    title = (
        f"{x_metric.display_name} vs perplexity (per-round) · "
        f"n={len(all_xs)} round-points across {len(runs)} runs · {pearson_text}"
    )
    fig.update_layout(
        title=dict(text=title, x=0.0, xanchor="left"),
        xaxis=dict(title=x_metric.x_axis_label),
        yaxis=dict(title="perplexity (mean per-token surprisal, nats, gpt2)"),
        height=520,
        margin=dict(t=70, b=40, l=60, r=20),
        legend=dict(orientation="h", y=-0.18),
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
            urls.append(run_url(frontend_base=frontend_base, run_id=run.run_id))
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
                "pearson(metric, success)": ("n/a" if pearson is None else f"{pearson:.3f}"),
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
                "n/a" if overall_pearson is None else f"{overall_pearson:.3f}"
            ),
        }
    )
    st.markdown("### Summary")
    st.dataframe(rows, width="stretch", hide_index=True)


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Verbosity tab body."""
    run_filter = seed_mode_filter.render_filters(key_prefix="verbosity")
    evaluated = seed_mode_filter.apply(evaluated=evaluated, run_filter=run_filter)
    scenario_name = _render_scenario_selector(evaluated=evaluated)
    if scenario_name is None:
        st.info("No evaluated runs found.")
        return
    all_runs = list_verbosity_runs(evaluated_runs=evaluated, scenario_name=scenario_name)
    if not all_runs:
        st.info(
            f"No baseline or resume runs in scenario `{scenario_name}` evaluated yet. "
            "Add the 'baseline' or 'resume' label and run `schmidt evaluate` with "
            "the language metrics."
        )
        return
    metric = _render_metric_selector()
    frontend_base = render_frontend_base(streamlit_key="verbosity_frontend_base")
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
    maybe_open_clicked_run(chart_event=chart_event, session_key="verbosity_last_opened_url")
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
    maybe_open_clicked_run(chart_event=per_round_event, session_key="verbosity_last_opened_url")
    st.markdown("### Verbosity vs perplexity (per round)")
    st.caption(
        "One point per (run, round) joining the run's per-round verbosity "
        "with its per-round perplexity. Coloured by budget bucket. The "
        "Pearson correlation in the title makes the inverse MCR/MCM-vs-PPL "
        "trend explicit (PPL as a downstream side effect of compressing "
        "for a narrow channel)."
    )
    x_metric = _render_verbosity_x_selector()
    vs_ppl_fig = _build_verbosity_vs_perplexity_figure(
        runs=filtered,
        x_metric=x_metric,
        frontend_base=frontend_base,
    )
    if vs_ppl_fig is None:
        st.info(
            "No selected runs have both per-round verbosity and per-round "
            "perplexity. Run `schmidt evaluate <scenario> --metrics "
            f"{x_metric.display_name},perplexity ...` first."
        )
        return
    vs_ppl_event = st.plotly_chart(
        vs_ppl_fig,
        width="stretch",
        key="verbosity_vs_ppl_chart",
        on_select="rerun",
        selection_mode=("points",),
    )
    maybe_open_clicked_run(chart_event=vs_ppl_event, session_key="verbosity_last_opened_url")
