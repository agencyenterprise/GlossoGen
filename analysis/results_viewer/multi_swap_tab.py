"""Streamlit tab visualising in-run agent swaps.

Two subtabs:

- **Per-run**: bar chart of round-success per phase for one selected run, with
  per-round green/red strip and a phase breakdown table.
- **Cohort overlay**: aggregate two label-defined cohorts (e.g.
  ``multi_swap_baseline`` vs ``multi_swap_baseline_postmortem_on``) on a shared
  per-round success curve and per-phase probe replica self-similarity chart.

Only runs containing at least one ``AgentSwappedMidRun`` event are eligible.
"""

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

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
_COHORT_PALETTE = ["#1E40AF", "#B91C1C", "#15803D", "#7C3AED", "#EA580C"]
_PHASE_BY_CUTOFF = {11: "A", 21: "B", 31: "C", 41: "D"}
_PHASE_ORDER = ["A", "B", "C", "D"]


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


def _render_per_run(evaluated: list[EvaluatedRun]) -> None:
    """Per-run bar chart, per-round strip, and phase breakdown table."""
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


def _per_round_success(jsonl_path: Path) -> dict[int, bool]:
    """Walk one run's JSONL and return ``round_number → success``."""
    per_round: dict[int, bool] = {}
    with jsonl_path.open() as fh:
        for line in fh:
            if '"round_result_recorded"' not in line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") != "round_result_recorded":
                continue
            per_round[event["round_number"]] = bool(event["success"])
    return per_round


def _has_simulation_ended(jsonl_path: Path) -> bool:
    with jsonl_path.open() as fh:
        for line in fh:
            if '"simulation_ended"' in line:
                return True
    return False


def _run_probe_phase_similarity(probe_path: Path) -> dict[str, float]:
    """Reduce one run's replica-self-similarity payload to one scalar per phase."""
    payload = json.loads(probe_path.read_text())
    groups = payload.get("groups", [])
    by_phase: dict[str, list[float]] = {p: [] for p in _PHASE_ORDER}
    for group in groups:
        cutoff = group.get("cutoff_round")
        phase = _PHASE_BY_CUTOFF.get(int(cutoff)) if cutoff is not None else None
        if phase is None:
            continue
        cells = group.get("cells", [])
        values = [cell.get("value") for cell in cells if cell.get("value") is not None]
        if values:
            by_phase[phase].append(mean(values))
    return {phase: (mean(values) if values else float("nan")) for phase, values in by_phase.items()}


def _gather_cohort(
    evaluated: list[EvaluatedRun], label: str, exclude_label: str | None
) -> list[EvaluatedRun]:
    """Filter ``evaluated`` to runs whose labels.json contains ``label`` and
    NOT ``exclude_label``. Reads labels.json directly so the cohort filter is
    robust against any label-shape changes elsewhere."""
    out: list[EvaluatedRun] = []
    for run in evaluated:
        labels_path = run.run_dir / "labels.json"
        if not labels_path.exists():
            continue
        try:
            labels = json.loads(labels_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if label not in labels:
            continue
        if exclude_label is not None and exclude_label in labels:
            continue
        out.append(run)
    return out


def _per_round_rate(
    cohort: list[dict[int, bool]], total_rounds: int
) -> tuple[list[float], list[float], list[int]]:
    means: list[float] = []
    ses: list[float] = []
    ns: list[int] = []
    for round_number in range(1, total_rounds + 1):
        values = [1.0 if run.get(round_number) else 0.0 for run in cohort if round_number in run]
        if values:
            mean_value = mean(values)
            se_value = stdev(values) / (len(values) ** 0.5) if len(values) > 1 else 0.0
        else:
            mean_value = 0.0
            se_value = 0.0
        means.append(mean_value)
        ses.append(se_value)
        ns.append(len(values))
    return means, ses, ns


def _per_phase_similarity_stats(
    cohort: list[dict[str, float]],
) -> tuple[list[float], list[float], list[int]]:
    means: list[float] = []
    ses: list[float] = []
    ns: list[int] = []
    for phase in _PHASE_ORDER:
        values = [
            run[phase] for run in cohort if phase in run and run[phase] == run[phase]  # filter NaN
        ]
        if values:
            mean_value = mean(values)
            se_value = stdev(values) / (len(values) ** 0.5) if len(values) > 1 else 0.0
        else:
            mean_value = float("nan")
            se_value = 0.0
        means.append(mean_value)
        ses.append(se_value)
        ns.append(len(values))
    return means, ses, ns


def _discover_cohort_labels(evaluated: list[EvaluatedRun]) -> list[str]:
    """Return every distinct label that appears on ≥2 evaluated runs."""
    counts: dict[str, int] = defaultdict(int)
    for run in evaluated:
        labels_path = run.run_dir / "labels.json"
        if not labels_path.exists():
            continue
        try:
            labels = json.loads(labels_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for lbl in labels:
            counts[lbl] += 1
    return sorted([lbl for lbl, n in counts.items() if n >= 2])


def _build_round_success_chart(
    cohorts: list[tuple[str, list[dict[int, bool]]]],
    total_rounds: int,
) -> go.Figure:
    """Per-round success curve with one line per cohort, ± SE bars + phase shading."""
    fig = go.Figure()
    phase_spans = [
        ("Phase A", 1, 10, "rgba(254, 226, 226, 0.45)"),
        ("Phase B", 11, 20, "rgba(254, 243, 199, 0.45)"),
        ("Phase C", 21, 30, "rgba(220, 252, 231, 0.45)"),
        ("Phase D", 31, 40, "rgba(219, 234, 254, 0.45)"),
    ]
    for name, start, end, colour in phase_spans:
        fig.add_vrect(x0=start - 0.5, x1=end + 0.5, fillcolor=colour, line_width=0, layer="below")
        fig.add_annotation(
            x=(start + end) / 2,
            y=1.05,
            text=name,
            showarrow=False,
            font=dict(size=11),
            xref="x",
            yref="paper",
        )
    rounds = list(range(1, total_rounds + 1))
    for index, (cohort_name, cohort_data) in enumerate(cohorts):
        if not cohort_data:
            continue
        colour = _COHORT_PALETTE[index % len(_COHORT_PALETTE)]
        means, ses, _ = _per_round_rate(cohort=cohort_data, total_rounds=total_rounds)
        fig.add_trace(
            go.Scatter(
                x=rounds,
                y=means,
                error_y=dict(type="data", array=ses, visible=True),
                mode="lines+markers",
                name=f"{cohort_name} (n={len(cohort_data)})",
                line=dict(color=colour, width=2),
                marker=dict(color=colour, size=7),
            )
        )
    fig.update_layout(
        title="Per-round success across the 4-phase timeline",
        xaxis=dict(title="Round", range=[0.5, total_rounds + 0.5]),
        yaxis=dict(
            title="Round success rate (mean across replicas)", range=[-0.05, 1.1], tickformat=".0%"
        ),
        height=460,
        margin=dict(t=70, b=50, l=60, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="left", x=0),
    )
    return fig


def _build_phase_similarity_chart(
    cohorts: list[tuple[str, list[dict[str, float]]]],
) -> go.Figure:
    """Per-phase probe replica self-similarity with one point series per cohort."""
    fig = go.Figure()
    x_positions = list(range(len(_PHASE_ORDER)))
    for index, (cohort_name, cohort_data) in enumerate(cohorts):
        if not cohort_data:
            continue
        colour = _COHORT_PALETTE[index % len(_COHORT_PALETTE)]
        means, ses, _ = _per_phase_similarity_stats(cohort=cohort_data)
        offset = (index - (len(cohorts) - 1) / 2) * 0.12
        fig.add_trace(
            go.Scatter(
                x=[x + offset for x in x_positions],
                y=means,
                error_y=dict(type="data", array=ses, visible=True),
                mode="markers",
                name=f"{cohort_name} (n={len(cohort_data)})",
                marker=dict(color=colour, size=12, symbol="circle"),
            )
        )
    fig.update_layout(
        title="Probe replica self-similarity per phase",
        xaxis=dict(
            title="Phase (probe cutoff at phase end)",
            tickmode="array",
            tickvals=x_positions,
            ticktext=[f"Phase {p}" for p in _PHASE_ORDER],
        ),
        yaxis=dict(title="Mean replica self-similarity (Levenshtein)"),
        height=430,
        margin=dict(t=70, b=80, l=60, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.22, xanchor="left", x=0),
    )
    return fig


def _render_cohort_overlay(evaluated: list[EvaluatedRun]) -> None:
    """Multi-cohort overlay: per-round success curve + per-phase probe similarity."""
    st.markdown(
        "Compare cohorts of multi-swap runs by label. Each selected label "
        "defines one cohort; the two charts overlay all selected cohorts on "
        "shared axes for direct comparison."
    )
    cohort_labels = _discover_cohort_labels(evaluated=evaluated)
    if not cohort_labels:
        st.info("No cohort labels found (need ≥2 runs sharing a label).")
        return
    default_labels = [
        lbl
        for lbl in ("multi_swap_baseline", "multi_swap_baseline_postmortem_on")
        if lbl in cohort_labels
    ] or cohort_labels[:2]
    selected = st.multiselect(
        label="Cohorts (one per label)",
        options=cohort_labels,
        default=default_labels,
        key="multi_swap_cohort_picker",
    )
    if not selected:
        st.info("Select at least one cohort label.")
        return
    total_rounds = int(
        st.number_input(
            label="Total rounds (x-axis range for the round-success curve)",
            min_value=10,
            max_value=200,
            value=40,
            step=5,
            key="multi_swap_cohort_total_rounds",
        )
    )

    # Build per-cohort round-success data + probe data
    cohort_round_data: list[tuple[str, list[dict[int, bool]]]] = []
    cohort_probe_data: list[tuple[str, list[dict[str, float]]]] = []
    cohort_run_lists: dict[str, list[EvaluatedRun]] = {}
    for label in selected:
        # Find label-exclusivity: if `multi_swap_baseline` is selected and
        # `multi_swap_baseline_postmortem_on` exists as a separate cohort, we
        # need to exclude the latter from the former's filter (since
        # `multi_swap_baseline` is a substring/superset label).
        exclude = None
        for other in selected:
            if other != label and other.startswith(label):
                exclude = other
                break
        runs = _gather_cohort(evaluated=evaluated, label=label, exclude_label=exclude)
        cohort_run_lists[label] = runs

        # Round-success: read JSONL for each run that has simulation_ended
        round_data: list[dict[int, bool]] = []
        for run in runs:
            jsonl = run.run_dir / f"{run.scenario_name}.jsonl"
            if jsonl.exists() and _has_simulation_ended(jsonl_path=jsonl):
                round_data.append(_per_round_success(jsonl_path=jsonl))
        cohort_round_data.append((label, round_data))

        # Probe similarity: read protocol_probe_replica_self_similarity.json
        probe_data: list[dict[str, float]] = []
        for run in runs:
            probe_path = run.run_dir / "protocol_probe_replica_self_similarity.json"
            if probe_path.exists():
                probe_data.append(_run_probe_phase_similarity(probe_path=probe_path))
        cohort_probe_data.append((label, probe_data))

    # Summary table of cohort sizes
    summary_rows = []
    for label in selected:
        runs = cohort_run_lists[label]
        round_n = len(
            [
                r
                for r in runs
                if (r.run_dir / f"{r.scenario_name}.jsonl").exists()
                and _has_simulation_ended(jsonl_path=(r.run_dir / f"{r.scenario_name}.jsonl"))
            ]
        )
        probe_n = sum(
            1 for r in runs if (r.run_dir / "protocol_probe_replica_self_similarity.json").exists()
        )
        summary_rows.append(
            {
                "Cohort": label,
                "Total runs": len(runs),
                "Finished (in round-success chart)": round_n,
                "With probes (in similarity chart)": probe_n,
            }
        )
    st.dataframe(summary_rows, hide_index=True, use_container_width=True)

    if all(not data for _, data in cohort_round_data) and all(
        not data for _, data in cohort_probe_data
    ):
        st.warning("Selected cohorts have no finished runs or probe data yet.")
        return
    st.markdown("---")
    st.subheader("Round-success curve")
    fig_rounds = _build_round_success_chart(cohorts=cohort_round_data, total_rounds=total_rounds)
    st.plotly_chart(fig_rounds, use_container_width=True, key="multi_swap_cohort_rounds_chart")

    st.markdown("---")
    st.subheader("Probe replica self-similarity per phase")
    st.caption(
        "Within (agent, question, cutoff), mean off-diagonal pairwise similarity "
        "of the 3 probe replicas. Higher = more stable protocol description. "
        "Cutoffs 11/21/31/41 map to end of phases A/B/C/D."
    )
    fig_sim = _build_phase_similarity_chart(cohorts=cohort_probe_data)
    st.plotly_chart(fig_sim, use_container_width=True, key="multi_swap_cohort_similarity_chart")


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the multi-swap tab body: Per-run + Cohort overlay subtabs."""
    per_run_panel, cohort_panel = st.tabs(["Per-run", "Cohort overlay"])
    with per_run_panel:
        _render_per_run(evaluated=evaluated)
    with cohort_panel:
        _render_cohort_overlay(evaluated=evaluated)
