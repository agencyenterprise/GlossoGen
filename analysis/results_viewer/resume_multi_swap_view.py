"""Per-phase round-success comparison between a source run and its resume replicas.

Used by the Resume tab's *Multi-swap* subtab. Picks a source run, fetches its
``MultiSwapRun.phases`` plus the phases of every resume replica targeting that
source, and renders a grouped bar chart (source bar + replica-mean bar with
replica dots overlaid) plus a comparison table aligned by phase label.

The source's own phases are read via
:func:`analysis.results_viewer.multi_swap_data.build_multi_swap_run`; replicas
come from the evaluated catalog already loaded by the caller.
"""

from typing import NamedTuple

import plotly.graph_objects as go
import streamlit as st

from analysis.results_viewer.multi_swap_data import MultiSwapRun, PhaseScore, build_multi_swap_run
from analysis.results_viewer.resume_data import ResumeRun
from analysis.results_viewer.run_catalog import EvaluatedRun
from analysis.results_viewer.run_link import run_url

_SOURCE_COLOR = "#0EA5E9"
_REPLICA_MEAN_COLOR = "#A855F7"
_REPLICA_DOT_COLOR = "#7E22CE"


class _ReplicaPhaseScore(NamedTuple):
    """A single replica's outcome on one aligned phase."""

    run_id: str
    won: int
    total: int
    score: float
    url: str


class _AlignedPhase(NamedTuple):
    """One phase row aligned between source and N replicas.

    ``replica_scores`` is a parallel list of per-replica outcomes; entries are
    ``None`` when a replica did not reach that phase (e.g. ran out of rounds).
    """

    phase_index: int
    label: str
    round_start: int
    round_end: int
    swap_label: str
    source_score: PhaseScore
    replica_scores: list[_ReplicaPhaseScore | None]


def _format_swap_label(phase: PhaseScore, source_run: MultiSwapRun) -> str:
    """One-line description of the swap that opens ``phase``."""
    if phase.swap is None:
        agent_models = ", ".join(
            f"{agent_id}={model}"
            for agent_id, model in sorted(source_run.initial_agent_models.items())
        )
        return f"initial: {agent_models}"
    return f"swap {phase.swap.agent_id} → {phase.swap.new_model} @ r{phase.swap.round_number}"


def _align_phases(
    source_run: MultiSwapRun,
    replica_runs: list[MultiSwapRun],
    frontend_base: str,
) -> list[_AlignedPhase]:
    """Match each source phase with the same phase in every replica.

    Alignment is positional by ``phase_index``: source phase 0 ↔ replica phase
    0, etc. ``scheduled_events`` is inherited from the source on resume, so
    replicas have the same swap boundaries and the same phase structure.
    """
    aligned: list[_AlignedPhase] = []
    for src_phase in source_run.phases:
        replica_scores: list[_ReplicaPhaseScore | None] = []
        for replica in replica_runs:
            replica_phase = next(
                (p for p in replica.phases if p.phase_index == src_phase.phase_index),
                None,
            )
            if replica_phase is None or replica_phase.total == 0:
                replica_scores.append(None)
                continue
            replica_scores.append(
                _ReplicaPhaseScore(
                    run_id=replica.run_id,
                    won=replica_phase.won,
                    total=replica_phase.total,
                    score=replica_phase.score,
                    url=run_url(frontend_base=frontend_base, run_id=replica.run_id),
                )
            )
        aligned.append(
            _AlignedPhase(
                phase_index=src_phase.phase_index,
                label=src_phase.label,
                round_start=src_phase.round_start,
                round_end=src_phase.round_end,
                swap_label=_format_swap_label(phase=src_phase, source_run=source_run),
                source_score=src_phase,
                replica_scores=replica_scores,
            )
        )
    return aligned


def _replica_mean(scores: list[_ReplicaPhaseScore | None]) -> float | None:
    """Mean replica score for one phase, or ``None`` when no replicas reached it."""
    values = [s.score for s in scores if s is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _build_comparison_chart(aligned: list[_AlignedPhase]) -> go.Figure:
    """Source bar + replica-mean bar grouped per phase, with replica dots overlaid."""
    labels = [p.label for p in aligned]
    source_y = [p.source_score.score for p in aligned]
    source_text = [
        f"{p.source_score.won}/{p.source_score.total}<br>({round(p.source_score.score * 100)}%)"
        for p in aligned
    ]
    replica_mean_y: list[float] = []
    replica_mean_text: list[str] = []
    for p in aligned:
        mean = _replica_mean(scores=p.replica_scores)
        if mean is None:
            replica_mean_y.append(0.0)
            replica_mean_text.append("—")
            continue
        replica_mean_y.append(mean)
        present = [s for s in p.replica_scores if s is not None]
        replica_mean_text.append(f"mean of {len(present)}<br>({round(mean * 100)}%)")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=source_y,
            text=source_text,
            textposition="inside",
            marker_color=_SOURCE_COLOR,
            name="Source",
            hovertemplate="Source · %{x}<br>%{text}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=labels,
            y=replica_mean_y,
            text=replica_mean_text,
            textposition="inside",
            marker_color=_REPLICA_MEAN_COLOR,
            name="Replicas (mean)",
            hovertemplate="Replicas · %{x}<br>%{text}<extra></extra>",
        )
    )
    # Replica dots overlay so individual replica scores are visible alongside the mean bar.
    dot_x: list[str] = []
    dot_y: list[float] = []
    dot_hover: list[str] = []
    dot_urls: list[str] = []
    for p in aligned:
        for replica in p.replica_scores:
            if replica is None:
                continue
            dot_x.append(p.label)
            dot_y.append(replica.score)
            dot_hover.append(
                f"{replica.run_id}<br>{p.label}<br>"
                f"{replica.won}/{replica.total} ({round(replica.score * 100)}%)<br>"
                f"click to open · {replica.url}"
            )
            dot_urls.append(replica.url)
    if dot_x:
        fig.add_trace(
            go.Scatter(
                x=dot_x,
                y=dot_y,
                mode="markers",
                marker=dict(color=_REPLICA_DOT_COLOR, size=10, line=dict(color="white", width=1)),
                name="Replica",
                hovertext=dot_hover,
                hoverinfo="text",
                customdata=dot_urls,
                xaxis="x2",
            )
        )
    fig.update_layout(
        barmode="group",
        xaxis=dict(title="Phase"),
        xaxis2=dict(overlaying="x", showticklabels=False, showgrid=False),
        yaxis=dict(
            title="Fraction of phase rounds stabilized",
            range=[0.0, 1.05],
            tickformat=".0%",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=20, t=60, b=60),
        height=460,
    )
    return fig


def _render_comparison_table(aligned: list[_AlignedPhase]) -> None:
    """Comparison table with one row per phase: source vs each replica."""
    if not aligned:
        return
    replica_count = len(aligned[0].replica_scores)
    rows: list[dict[str, str]] = []
    for phase in aligned:
        row: dict[str, str] = {
            "Phase": phase.label,
            "Rounds": f"{phase.round_start}-{phase.round_end}",
            "Boundary": phase.swap_label,
            "Source": (
                f"{phase.source_score.won}/{phase.source_score.total} "
                f"({round(phase.source_score.score * 100)}%)"
            ),
        }
        for index in range(replica_count):
            replica = phase.replica_scores[index]
            if replica is None:
                row[f"Rep {index + 1}"] = "—"
                continue
            row[f"Rep {index + 1}"] = (
                f"{replica.won}/{replica.total} ({round(replica.score * 100)}%)"
            )
        mean = _replica_mean(scores=phase.replica_scores)
        row["Replica mean"] = "—" if mean is None else f"{round(mean * 100)}%"
        rows.append(row)
    st.dataframe(rows, width="stretch", hide_index=True)


def _pick_source(
    resumes_by_source: dict[str, list[ResumeRun]],
    key_prefix: str,
) -> str | None:
    """Streamlit selectbox listing every source with at least one multi-swap resume."""
    options = sorted(resumes_by_source)
    if not options:
        return None
    formatted = [f"{source} ({len(resumes_by_source[source])} replica(s))" for source in options]
    chosen_index = st.selectbox(
        label="Source run",
        options=range(len(options)),
        format_func=lambda i: formatted[i],
        key=f"{key_prefix}_source_picker",
    )
    return options[chosen_index]


def render(
    multi_swap_resumes: list[ResumeRun],
    evaluated: list[EvaluatedRun],
    frontend_base: str,
    key_prefix: str,
) -> None:
    """Render the Multi-swap subtab body: per-phase source-vs-replicas comparison."""
    if not multi_swap_resumes:
        st.info("No resume runs with in-run agent swaps in this scenario.")
        return
    resumes_by_source: dict[str, list[ResumeRun]] = {}
    for resume in multi_swap_resumes:
        resumes_by_source.setdefault(resume.source_run_id, []).append(resume)
    chosen_source = _pick_source(resumes_by_source=resumes_by_source, key_prefix=key_prefix)
    if chosen_source is None:
        return
    evaluated_by_run_id = {run.run_id: run for run in evaluated}
    source_evaluated = evaluated_by_run_id.get(chosen_source)
    if source_evaluated is None:
        st.warning(
            f"Source run `{chosen_source}` is not in the evaluated catalog. "
            "Run `schmidt evaluate` on it so its phase scores can be loaded."
        )
        return
    source_run = build_multi_swap_run(evaluated=source_evaluated)
    if source_run is None:
        st.warning(
            f"Source run `{chosen_source}` has no in-run agent swaps; its replicas "
            "would not have any either."
        )
        return
    replica_runs: list[MultiSwapRun] = []
    missing: list[str] = []
    for resume in resumes_by_source[chosen_source]:
        evaluated_run = evaluated_by_run_id.get(resume.run_id)
        if evaluated_run is None:
            missing.append(resume.run_id)
            continue
        replica = build_multi_swap_run(evaluated=evaluated_run)
        if replica is None:
            missing.append(resume.run_id)
            continue
        replica_runs.append(replica)
    if missing:
        st.caption(
            f"Skipped {len(missing)} replica(s) without a usable evaluation: "
            f"{', '.join(missing)}"
        )
    if not replica_runs:
        st.info(
            "No evaluated replicas for the chosen source. Run `schmidt evaluate` on the "
            "resume runs so their phase scores can be loaded."
        )
        return
    aligned = _align_phases(
        source_run=source_run,
        replica_runs=replica_runs,
        frontend_base=frontend_base,
    )
    st.caption(
        "Source bar vs replica-mean bar per phase, with each replica's score " "overlaid as a dot."
    )
    fig = _build_comparison_chart(aligned=aligned)
    st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_phase_comparison_chart")
    _render_comparison_table(aligned=aligned)
