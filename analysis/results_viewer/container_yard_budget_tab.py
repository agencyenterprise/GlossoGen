"""Streamlit tab analyzing container-yard runs under different budget constraints.

Two views, both scoped to the ``container_yard_stacking`` scenario:

1. **Round success vs budget** — one line per model (mean ± std across replicas)
   plus jittered replica dots, X = ``round_time_budget_seconds``. Shows how the
   per-round communication budget moves the success rate.
2. **Protocol at two rounds** — for two user-chosen focus rounds (default 7 and
   14), the first three link-channel messages of each run alongside that round's
   success flag, so the emergent protocol can be compared across budgets at an
   early vs a late round.
"""

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.container_yard_budget_data import (
    ContainerYardBudgetRun,
    FocusRound,
    list_container_yard_budget_runs,
)
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

_ROLE_ABBREVIATIONS = {
    "yard_operator": "YARD",
    "logistics_planner": "PLAN",
    "crane_operator": "CRANE",
    "intern": "INTERN",
}


def _render_focus_round_inputs() -> list[int]:
    """Two number inputs picking the early and late focus rounds (defaults 7 and 14)."""
    early_col, late_col = st.columns(2)
    early = early_col.number_input(
        label="Early focus round",
        min_value=1,
        value=7,
        step=1,
        key="cys_budget_focus_early",
    )
    late = late_col.number_input(
        label="Late focus round",
        min_value=1,
        value=14,
        step=1,
        key="cys_budget_focus_late",
    )
    ordered = sorted({int(early), int(late)})
    return ordered


def _render_model_filter(runs: list[ContainerYardBudgetRun]) -> set[str]:
    """Checkboxes for each distinct model in the data."""
    counts: dict[str, int] = {}
    for run in runs:
        counts[run.model] = counts.get(run.model, 0) + 1
    options = [(model, model, counts[model]) for model in sorted(counts)]
    return render_horizontal_checkboxes(
        title="Model",
        options=options,
        key_prefix="cys_budget_model_filter",
        initial_state=True,
    )


def _render_budget_filter(runs: list[ContainerYardBudgetRun]) -> set[int]:
    """Checkboxes for each distinct budget bucket present in the data."""
    counts: dict[int, int] = {}
    for run in runs:
        counts[run.budget] = counts.get(run.budget, 0) + 1
    options = [(str(b), str(b), counts[b]) for b in sorted(counts)]
    selected_keys = render_horizontal_checkboxes(
        title="Budget per round",
        options=options,
        key_prefix="cys_budget_budget_filter",
        initial_state=True,
    )
    return {int(key) for key in selected_keys}


def _build_success_figure(
    runs: list[ContainerYardBudgetRun],
    colour_by_series: dict[str, str],
    x_tickvals: list[int],
    frontend_base: str,
) -> go.Figure:
    """Budget → round-success figure: per-model mean ± std line plus replica dots."""
    fig = go.Figure()
    runs_by_series: dict[str, list[ContainerYardBudgetRun]] = {}
    for run in runs:
        runs_by_series.setdefault(run.model, []).append(run)
    stats = aggregate_buckets(
        items=runs,
        series_of=lambda r: r.model,
        x_of=lambda r: float(r.budget),
        value_of=lambda r: r.success_fraction,
    )
    stats_by_series: dict[str, list] = {}
    for stat in stats:
        stats_by_series.setdefault(stat.series, []).append(stat)
    for series, colour in colour_by_series.items():
        if series in stats_by_series:
            add_mean_trace(
                fig=fig,
                series=series,
                stats=stats_by_series[series],
                metric_display_name="round_success",
                colour=colour,
                dash="solid",
            )
    for series, colour in colour_by_series.items():
        bucket = runs_by_series.get(series, [])
        if not bucket:
            continue
        xs: list[float] = []
        ys: list[float] = []
        hover: list[str] = []
        urls: list[str] = []
        for index, run in enumerate(bucket):
            url = run_url(frontend_base=frontend_base, run_id=run.run_id)
            xs.append(jittered_x_linear(base_x=float(run.budget), index=index))
            ys.append(run.success_fraction)
            hover.append(
                f"{run.run_id}<br>{series}<br>budget={run.budget}<br>"
                f"round_success={run.success_fraction:.0%}<br>click to open · {url}"
            )
            urls.append(url)
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
            title="round_time_budget_seconds",
            tickmode="array",
            tickvals=x_tickvals,
            ticktext=[str(b) for b in x_tickvals],
        ),
        yaxis=dict(title="round success (mean ± std)", range=[-0.02, 1.02], tickformat=".0%"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=20, t=40, b=60),
        height=500,
    )
    return fig


def _success_glyph(succeeded: bool | None) -> str:
    """Render a round's success flag: ✓ / ✗ / — (not recorded)."""
    if succeeded is None:
        return "—"
    return "✓" if succeeded else "✗"


def _format_messages(focus: FocusRound) -> str:
    """Join a focus round's first messages as ``ROLE: text`` lines, or a placeholder."""
    if not focus.first_messages:
        return "(no link messages)"
    lines: list[str] = []
    for message in focus.first_messages:
        role = _ROLE_ABBREVIATIONS.get(message.sender, message.sender)
        lines.append(f"{role}: {message.text}")
    return "\n".join(lines)


def _render_protocol_table(
    runs: list[ContainerYardBudgetRun],
    focus_round_numbers: list[int],
    frontend_base: str,
) -> None:
    """Per-run table: each focus round's success flag next to its first messages.

    Rows are sorted by budget then model so the same focus round can be read
    top-to-bottom across budgets to see how the protocol tightens.
    """
    rows: list[dict[str, object]] = []
    for run in sorted(runs, key=lambda r: (r.budget, r.model, r.run_id)):
        focus_by_round = {focus.round_number: focus for focus in run.focus_rounds}
        row: dict[str, object] = {
            "model": run.model,
            "budget": run.budget,
            "overall success": f"{run.success_fraction:.0%}",
        }
        for round_number in focus_round_numbers:
            focus = focus_by_round.get(round_number)
            if focus is None:
                row[f"r{round_number} ✓"] = "—"
                row[f"r{round_number} first 3 messages"] = ""
                continue
            row[f"r{round_number} ✓"] = _success_glyph(succeeded=focus.succeeded)
            row[f"r{round_number} first 3 messages"] = _format_messages(focus=focus)
        row["url"] = run_url(frontend_base=frontend_base, run_id=run.run_id)
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
            **{
                f"r{n} first 3 messages": st.column_config.TextColumn(width="large")
                for n in focus_round_numbers
            },
        },
    )


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the Container-yard budget tab body."""
    focus_round_numbers = _render_focus_round_inputs()
    all_runs = list_container_yard_budget_runs(
        evaluated_runs=evaluated, focus_round_numbers=focus_round_numbers
    )
    if not all_runs:
        st.info(
            "No evaluated `container_yard_stacking` runs with a `round_success` "
            "measurement and a `round_time_budget_seconds` budget found. Run "
            "`schmidt evaluate container_yard_stacking --metrics round_success ...` "
            "on the runs you want included."
        )
        return
    frontend_base = render_frontend_base(streamlit_key="cys_budget_frontend_base")
    selected_models = _render_model_filter(runs=all_runs)
    selected_budgets = _render_budget_filter(runs=all_runs)
    if not selected_models:
        st.info("Select at least one model.")
        return
    if not selected_budgets:
        st.info("Select at least one budget bucket.")
        return
    filtered = [
        run for run in all_runs if run.model in selected_models and run.budget in selected_budgets
    ]
    if not filtered:
        st.info("No container-yard runs for the selected filters.")
        return
    colour_by_series = series_color_map(series_keys=sorted({r.model for r in filtered}))
    x_tickvals = sorted({r.budget for r in all_runs})
    st.markdown("### Round success vs budget")
    st.caption(
        "One line per model (mean ± std across replicas); faint dots are individual "
        "runs. X is the per-round communication budget — one character on the link "
        "channel costs one second of it."
    )
    fig = _build_success_figure(
        runs=filtered,
        colour_by_series=colour_by_series,
        x_tickvals=x_tickvals,
        frontend_base=frontend_base,
    )
    chart_event = st.plotly_chart(
        fig,
        width="stretch",
        key="cys_budget_chart",
        on_select="rerun",
        selection_mode=("points",),
    )
    maybe_open_clicked_run(chart_event=chart_event, session_key="cys_budget_last_opened_url")
    rounds_label = " and ".join(f"round {n}" for n in focus_round_numbers)
    st.markdown(f"### Protocol at {rounds_label}")
    st.caption(
        "First three link-channel messages of each focus round, next to that round's "
        "success flag (✓ / ✗ / — not recorded). Sorted by budget then model so the "
        "protocol can be compared across budgets at the same round."
    )
    _render_protocol_table(
        runs=filtered,
        focus_round_numbers=focus_round_numbers,
        frontend_base=frontend_base,
    )
