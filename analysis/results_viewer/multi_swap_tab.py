"""Streamlit tab visualising round-success per phase across in-run agent swaps.

Shows one bar chart per selected run: one bar per phase (A, B, C, D, …), with
height = phase round_success and Δ vs the previous phase annotated above each
bar. Below the chart, a table lists each phase's round window, swap event,
round count, wins, and score. Only runs containing at least one
``AgentSwappedMidRun`` event are eligible.
"""

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer import seed_mode_filter
from analysis.results_viewer.multi_swap_data import MultiSwapRun, PhaseScore, list_multi_swap_runs
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import render_frontend_base, run_url

_PHASE_BAR_COLOR = "#4F46E5"
_DELTA_POSITIVE_COLOR = "#15803D"
_DELTA_NEGATIVE_COLOR = "#B91C1C"
_DELTA_ZERO_COLOR = "#475569"


def _format_swap_text(phase: PhaseScore, multi_swap: MultiSwapRun) -> str:
    """One-line description of who swapped at the boundary opening this phase."""
    if phase.swap is None:
        agent_models = ", ".join(
            f"{agent_id}={model}"
            for agent_id, model in sorted(multi_swap.initial_agent_models.items())
        )
        return f"initial agents: {agent_models}"
    return (
        f"swapped {phase.swap.agent_id} → {phase.swap.new_model} "
        f"({phase.swap.new_provider}) at round {phase.swap.round_number}"
    )


def _delta_label(current: PhaseScore, previous: PhaseScore | None) -> str:
    """Δ pp from previous phase to current; empty string when no previous phase."""
    if previous is None:
        return ""
    delta_pp = round((current.score - previous.score) * 100)
    if delta_pp > 0:
        return f"+{delta_pp} pp"
    if delta_pp < 0:
        return f"{delta_pp} pp"
    return "0 pp"


def _delta_color(current: PhaseScore, previous: PhaseScore | None) -> str:
    """Annotation colour based on whether the phase improved over the previous."""
    if previous is None:
        return _DELTA_ZERO_COLOR
    delta = current.score - previous.score
    if delta > 0:
        return _DELTA_POSITIVE_COLOR
    if delta < 0:
        return _DELTA_NEGATIVE_COLOR
    return _DELTA_ZERO_COLOR


def _build_phase_chart(multi_swap: MultiSwapRun) -> go.Figure:
    """One Plotly bar chart with phases on X and round_success on Y."""
    phases = multi_swap.phases
    bar_x = [phase.label for phase in phases]
    bar_y = [phase.score for phase in phases]
    bar_text = [f"{phase.won}/{phase.total}<br>({round(phase.score * 100)}%)" for phase in phases]
    hover_text = [
        f"{phase.label}<br>Rounds {phase.round_start}–{phase.round_end}<br>"
        f"{_format_swap_text(phase=phase, multi_swap=multi_swap)}<br>"
        f"Score: {phase.won}/{phase.total} ({round(phase.score * 100)}%)"
        for phase in phases
    ]

    fig = go.Figure(
        data=[
            go.Bar(
                x=bar_x,
                y=bar_y,
                text=bar_text,
                textposition="inside",
                marker_color=_PHASE_BAR_COLOR,
                hovertext=hover_text,
                hoverinfo="text",
                name="Phase score",
            )
        ]
    )
    for index, phase in enumerate(phases):
        previous = phases[index - 1] if index > 0 else None
        delta_text = _delta_label(current=phase, previous=previous)
        if not delta_text:
            continue
        fig.add_annotation(
            x=phase.label,
            y=phase.score,
            yshift=24,
            text=f"<b>{delta_text}</b>",
            showarrow=False,
            font=dict(color=_delta_color(current=phase, previous=previous), size=13),
        )
    fig.update_layout(
        title=f"Round-success per phase — {multi_swap.run_id}",
        xaxis_title="Phase",
        yaxis_title="Fraction of phase rounds stabilized",
        yaxis=dict(range=[0.0, 1.05], tickformat=".0%"),
        height=440,
        margin=dict(t=70, b=40, l=60, r=20),
        showlegend=False,
    )
    return fig


def _render_phase_table(multi_swap: MultiSwapRun) -> None:
    """Tabular breakdown matching the bar chart, including round outcomes."""
    rows = []
    previous: PhaseScore | None = None
    for phase in multi_swap.phases:
        rows.append(
            {
                "Phase": phase.label,
                "Rounds": f"{phase.round_start}–{phase.round_end}",
                "Boundary event": _format_swap_text(phase=phase, multi_swap=multi_swap),
                "Score": f"{phase.won}/{phase.total} ({round(phase.score * 100)}%)",
                "Δ vs prev": _delta_label(current=phase, previous=previous),
            }
        )
        previous = phase
    st.dataframe(rows, hide_index=True, use_container_width=True)


def _render_round_strip(multi_swap: MultiSwapRun) -> None:
    """Compact per-round green/red strip across all phases for at-a-glance reading."""
    phase_outcomes = []
    for phase in multi_swap.phases:
        for round_number in sorted(phase.round_outcomes):
            phase_outcomes.append(
                {
                    "round": round_number,
                    "phase": phase.label,
                    "won": phase.round_outcomes[round_number],
                }
            )
    if not phase_outcomes:
        return
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=[entry["round"] for entry in phase_outcomes],
            y=[1 for _ in phase_outcomes],
            marker_color=["#15803D" if entry["won"] else "#B91C1C" for entry in phase_outcomes],
            hovertext=[
                f"Round {entry['round']} — {entry['phase']} — "
                f"{'stabilized' if entry['won'] else 'lost'}"
                for entry in phase_outcomes
            ],
            hoverinfo="text",
            name="round outcome",
        )
    )
    for phase in multi_swap.phases:
        if phase.swap is None:
            continue
        fig.add_vline(
            x=phase.round_start - 0.5,
            line_color="#1E293B",
            line_dash="dash",
            line_width=1,
        )
        fig.add_annotation(
            x=phase.round_start - 0.5,
            y=1.05,
            text=f"swap {phase.swap.agent_id}",
            showarrow=False,
            font=dict(size=10, color="#1E293B"),
            yanchor="bottom",
        )
    fig.update_layout(
        title="Per-round outcomes (green = stabilized, red = lost)",
        height=160,
        margin=dict(t=40, b=20, l=40, r=20),
        showlegend=False,
        xaxis_title="Round",
        yaxis=dict(visible=False, range=[0, 1.1]),
        bargap=0.05,
    )
    st.plotly_chart(fig, use_container_width=True)


def _run_picker_label(multi_swap: MultiSwapRun) -> str:
    """Picker label combining run id, primary model, swap count, and labels."""
    label_suffix = f" [{', '.join(multi_swap.labels)}]" if multi_swap.labels else ""
    return (
        f"{multi_swap.run_id} • {multi_swap.primary_model} • "
        f"{len(multi_swap.swaps)} swap(s){label_suffix}"
    )


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the multi-swap tab body."""
    run_filter = seed_mode_filter.render_filters(key_prefix="multi_swap")
    evaluated = seed_mode_filter.apply(evaluated=evaluated, run_filter=run_filter)
    st.markdown(
        "Visualise per-phase round-success for runs with one or more in-run "
        "agent swaps. Each bar is one phase between adjacent swaps; Δ pp "
        "above the bar shows change vs the previous phase."
    )
    runs = list_multi_swap_runs(evaluated_runs=evaluated)
    if not runs:
        st.info(
            "No runs with `AgentSwappedMidRun` events found. Multi-swap runs "
            "are produced by the in-run scheduler (`scheduled_events` in knobs)."
        )
        return
    frontend_base = render_frontend_base(streamlit_key="multi_swap_frontend_base")
    options = {_run_picker_label(multi_swap=run): run for run in runs}
    chosen_label = st.selectbox(
        label="Run",
        options=list(options.keys()),
        index=0,
        key="multi_swap_run_picker",
    )
    multi_swap = options[chosen_label]
    target_url = run_url(frontend_base=frontend_base, run_id=multi_swap.run_id)
    st.markdown(f"[Open run in frontend ↗]({target_url})")
    st.plotly_chart(_build_phase_chart(multi_swap=multi_swap), use_container_width=True)
    _render_round_strip(multi_swap=multi_swap)
    st.markdown("**Phase breakdown**")
    _render_phase_table(multi_swap=multi_swap)
