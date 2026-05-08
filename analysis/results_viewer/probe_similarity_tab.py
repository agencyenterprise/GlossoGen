"""Streamlit "Probe similarity" tab — Levenshtein-based comparisons over probe responses.

Four sub-views, each driven by data the three veyru similarity metrics
already wrote to disk plus the raw ``protocol_probe_responses.jsonl`` rows
loaded by ``probe_similarity_data.list_probe_similarity_runs``:

* Replica self-similarity — within-run, per (agent, question, cutoff)
  matrix from ``protocol_probe_replica_self_similarity.json``.
* Agent-pair similarity — within-run, per (question, cutoff) matrix from
  ``protocol_probe_agent_pair_similarity.json`` (two-team / cross-team
  runs only).
* Cross-run model-vs-model — live pairwise computation over raw probe
  rows gathered across every selected run for a chosen question.
* Cutoff trajectory — within-run, per-(agent, question) adjacent-cutoff
  series from ``protocol_probe_cutoff_trajectory.json``.

A single multi-select at the top of the tab drives every sub-view: each
within-run sub-view leads with a comparison bar chart of overall scores
across the selected runs, then offers a detail drill-down on one chosen
run. The cross-run sub-view aggregates raw rows only from the selected
runs. The cross-run sub-view is the only place this tab does live
Levenshtein work; the other three render straight from the artifacts.
"""

import logging

import plotly.graph_objects as go
import streamlit as st
from rapidfuzz.distance import Levenshtein

from analysis.results_viewer.probe_similarity_data import (
    ProbeSimilarityRun,
    list_probe_similarity_runs,
)
from analysis.results_viewer.run_catalog import EvaluatedRun
from schmidt.evaluation.protocol_probe_response import ProtocolProbeResponse
from schmidt.scenarios.veyru.evaluation.protocol_probe_agent_pair_similarity_metric import (
    AgentPairSimGroup,
)
from schmidt.scenarios.veyru.evaluation.protocol_probe_cutoff_trajectory_metric import (
    CutoffTrajectoryGroup,
)
from schmidt.scenarios.veyru.evaluation.protocol_probe_replica_self_similarity_metric import (
    ReplicaSelfSimGroup,
)

logger = logging.getLogger(__name__)

_HEATMAP_COLORSCALE = "Viridis"
_BAR_COLOR = "#4F46E5"


def _format_cutoff(cutoff_round: int | None) -> str:
    """Human-readable label for a probe ``cutoff_round`` value."""
    if cutoff_round is None:
        return "end-of-run"
    return f"round {cutoff_round}"


def _truncate(text: str, limit: int) -> str:
    """Trim ``text`` to ``limit`` chars, suffixing ``…`` if it was longer."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _matrix_from_cells(cells_by_pair: dict[tuple[int, int], float], size: int) -> list[list[float]]:
    """Reconstruct a symmetric N×N matrix from the strict-upper-triangle cell list."""
    matrix: list[list[float]] = [[1.0 if i == j else 0.0 for j in range(size)] for i in range(size)]
    for (i, j), value in cells_by_pair.items():
        matrix[i][j] = value
        matrix[j][i] = value
    return matrix


def _run_picker_label(probe_run: ProbeSimilarityRun) -> str:
    """One-line picker label combining run_id, model, and label list."""
    label_str = ",".join(probe_run.labels) if probe_run.labels else "—"
    return f"{probe_run.run_id} · {probe_run.primary_model} · labels=[{label_str}]"


def _comparison_bar_chart(
    title: str,
    runs: list[ProbeSimilarityRun],
    score_by_run_id: dict[str, float],
    yaxis_title: str,
) -> go.Figure:
    """Stacked bar chart with one bar per selected run, height = its overall score.

    Runs with no score (artifact missing) are omitted from the chart.
    """
    in_chart = [run for run in runs if run.run_id in score_by_run_id]
    bar_labels = [f"{run.run_id}<br>{run.primary_model}" for run in in_chart]
    bar_values = [score_by_run_id[run.run_id] for run in in_chart]
    fig = go.Figure(
        data=go.Bar(
            x=bar_labels,
            y=bar_values,
            marker_color=_BAR_COLOR,
            text=[f"{value:.3f}" for value in bar_values],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Run",
        yaxis=dict(title=yaxis_title, range=[0.0, 1.05]),
        height=380,
        margin=dict(t=60, b=120, l=60, r=20),
        showlegend=False,
    )
    return fig


def _replica_self_groups_to_dataframe_rows(
    groups: list[ReplicaSelfSimGroup],
) -> list[dict[str, str | float | int]]:
    """Flatten replica-self groups into table rows for at-a-glance reading."""
    rows: list[dict[str, str | float | int]] = []
    for group in groups:
        rows.append(
            {
                "agent": group.agent_id,
                "model": group.model,
                "question": group.question_id,
                "cutoff": _format_cutoff(cutoff_round=group.cutoff_round),
                "replicas": len(group.response_texts),
                "mean similarity": round(group.mean_similarity, 3),
                "first response": _truncate(text=group.response_texts[0], limit=60),
            }
        )
    return rows


def _drill_run_picker(
    label: str,
    runs: list[ProbeSimilarityRun],
    state_key: str,
) -> ProbeSimilarityRun:
    """Single-run selectbox limited to the runs that have the relevant artifact."""
    options = {_run_picker_label(probe_run=run): run for run in runs}
    chosen_label = st.selectbox(
        label=label,
        options=list(options.keys()),
        index=0,
        key=state_key,
    )
    return options[chosen_label]


def _render_replica_self_subview(probe_runs: list[ProbeSimilarityRun]) -> None:
    """Sub-view 2 — within-run replica self-similarity, per group.

    Renders an across-run comparison bar chart at the top, then a
    drill-down detail view for one chosen run.
    """
    title_col, info_col = st.columns([8, 1])
    with title_col:
        st.markdown("### Replica self-similarity")
    with info_col:
        with st.popover("ⓘ", help="What this metric measures"):
            st.markdown(
                "**The question this answers:** when the same agent is asked "
                "the same probe question several times in a row (under "
                "`--probe-replicas N`), does it produce the same answer every "
                "time, or does it drift?\n\n"
                "**How it's computed:** for every `(agent, question, "
                "cutoff_round)` group with at least 2 replicas, we compute "
                "normalized Levenshtein similarity on `response_text` for "
                "every pair of replicas, then take the mean. The bar shown "
                "for each run is the macro mean of those per-group means "
                "(mean of means, so groups with more replicas don't "
                "dominate).\n\n"
                "**How to read the score** (range 0–1):\n"
                "- `1.0` — every replica produced the byte-identical response. "
                "The agent's protocol has converged to a deterministic "
                "surface form (e.g. all replicas emit the code `!AC` for the "
                "same symptom). This is the expected signal for a stable, "
                "converged protocol — saturation is a feature, not a bug.\n"
                "- `~0.7–0.95` — replicas mostly agree but with small surface "
                "variation (paraphrasing, word-order shuffles, optional "
                "words).\n"
                "- `< 0.5` — replicas disagree substantively. The agent has "
                "not converged on a single way of answering this kind of "
                "input.\n\n"
                "**What it does *not* tell you:** whether two different "
                "agents (or two different models) answer the same way — "
                "that's the *Agent-pair* and *Cross-run model-vs-model* "
                "sub-views. Self-similarity is purely about one agent's "
                "consistency with itself."
            )
    runs_with_artifact = [run for run in probe_runs if run.replica_self is not None]
    if not runs_with_artifact:
        st.info(
            "None of the selected runs have a replica-self artifact. Run "
            "`schmidt evaluate ... --metrics protocol_probe_replica_self_similarity` "
            "first."
        )
        return
    score_by_run_id = {
        run.run_id: run.replica_self.overall_mean_similarity
        for run in runs_with_artifact
        if run.replica_self is not None
    }
    fig = _comparison_bar_chart(
        title="Overall replica self-similarity per run",
        runs=runs_with_artifact,
        score_by_run_id=score_by_run_id,
        yaxis_title="Macro mean similarity",
    )
    st.plotly_chart(fig, width="stretch")
    st.markdown("---")
    st.markdown("**Drill into one run**")
    chosen = _drill_run_picker(
        label="Run",
        runs=runs_with_artifact,
        state_key="probe_similarity_replica_drill_run",
    )
    if chosen.replica_self is None:
        return
    artifact = chosen.replica_self
    st.markdown(
        f"**Overall mean self-similarity**: `{artifact.overall_mean_similarity:.3f}` "
        f"across `{len(artifact.groups)}` (agent, question, cutoff) groups."
    )
    rows = _replica_self_groups_to_dataframe_rows(groups=artifact.groups)
    st.dataframe(rows, hide_index=True, width="stretch")
    group_options = {
        (
            f"{group.agent_id} / {group.question_id} / "
            f"{_format_cutoff(cutoff_round=group.cutoff_round)}"
        ): group
        for group in artifact.groups
    }
    chosen_label = st.selectbox(
        label="Inspect one group's replica × replica matrix",
        options=list(group_options.keys()),
        index=0,
        key="probe_similarity_replica_group_picker",
    )
    chosen_group = group_options[chosen_label]
    cells_by_pair = {(cell.i, cell.j): cell.value for cell in chosen_group.cells}
    matrix = _matrix_from_cells(
        cells_by_pair=cells_by_pair,
        size=len(chosen_group.replica_indices),
    )
    labels = [f"replica {idx}" for idx in chosen_group.replica_indices]
    fig = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=labels,
            y=labels,
            colorscale=_HEATMAP_COLORSCALE,
            zmin=0.0,
            zmax=1.0,
            text=[[f"{value:.2f}" for value in row] for row in matrix],
            texttemplate="%{text}",
        )
    )
    fig.update_layout(
        title=f"{chosen_group.agent_id} / {chosen_group.question_id} / "
        f"{_format_cutoff(cutoff_round=chosen_group.cutoff_round)}",
        height=420,
        margin=dict(t=60, b=40, l=80, r=40),
    )
    st.plotly_chart(fig, width="stretch")
    st.markdown("**Replica responses**")
    response_rows = [
        {
            "replica": idx,
            "response": _truncate(text=text, limit=200),
        }
        for idx, text in zip(chosen_group.replica_indices, chosen_group.response_texts, strict=True)
    ]
    st.dataframe(response_rows, hide_index=True, width="stretch")


def _render_agent_pair_subview(probe_runs: list[ProbeSimilarityRun]) -> None:
    """Sub-view 1 — within-run agent-vs-agent matrix per question + cutoff."""
    title_col, info_col = st.columns([8, 1])
    with title_col:
        st.markdown("### Agent-pair similarity")
    with info_col:
        with st.popover("ⓘ", help="What this metric measures"):
            st.markdown(
                "**The question this answers:** in a two-team / cross-team "
                "run where two agents share the same role (e.g. two field "
                "observers, one per team), do they answer the same probe "
                "question the same way? In other words, did the two teams "
                "converge to the same protocol, or did each team build its "
                "own?\n\n"
                "**How it's computed:** for every `(question, cutoff_round)` "
                "group with at least 2 agents matching the question's role "
                "filter, the matrix cell `(a, b)` is the mean normalized "
                "Levenshtein similarity over every (replica of a × replica "
                "of b) pair on `response_text`. The bar shown for each run "
                "is the macro mean of those cell values across all "
                "(question, cutoff) groups.\n\n"
                "**How to read the score** (range 0–1):\n"
                "- `1.0` — both agents emit byte-identical responses. The "
                "two teams converged on the exact same protocol despite "
                "running independently.\n"
                "- `~0.5–0.9` — partial convergence: agents agree on some "
                "questions, diverge on others.\n"
                "- `< 0.3` — the two teams developed substantively different "
                "protocols (different codes, different message structure).\n\n"
                "**Single-team runs:** this metric does not apply — there is "
                "only one agent per role, so no pairs exist. The sub-view "
                "renders the *Pick at least one run* gate instead."
            )
    runs_with_artifact = [
        run for run in probe_runs if run.agent_pair is not None and run.agent_pair.groups
    ]
    if not runs_with_artifact:
        st.info(
            "None of the selected runs have an agent-pair artifact with "
            "groups. Single-team runs produce no agent pairs; for two-team / "
            "cross-team runs run `schmidt evaluate ... --metrics "
            "protocol_probe_agent_pair_similarity`."
        )
        return
    score_by_run_id = {
        run.run_id: run.agent_pair.overall_mean_similarity
        for run in runs_with_artifact
        if run.agent_pair is not None
    }
    fig = _comparison_bar_chart(
        title="Overall agent-pair similarity per run",
        runs=runs_with_artifact,
        score_by_run_id=score_by_run_id,
        yaxis_title="Macro mean similarity",
    )
    st.plotly_chart(fig, width="stretch")
    st.markdown(
        "Each bar is the macro mean cross-agent similarity across all "
        "(question, cutoff) groups in that run. Lower values indicate "
        "the agents in the same role developed divergent protocols."
    )
    st.markdown("---")
    st.markdown("**Drill into one run**")
    chosen = _drill_run_picker(
        label="Run",
        runs=runs_with_artifact,
        state_key="probe_similarity_agent_pair_drill_run",
    )
    if chosen.agent_pair is None:
        return
    artifact = chosen.agent_pair
    st.markdown(
        f"**Overall mean cross-agent similarity**: "
        f"`{artifact.overall_mean_similarity:.3f}` across "
        f"`{len(artifact.groups)}` (question, cutoff) groups."
    )
    group_options = {
        f"{group.question_id} / {_format_cutoff(cutoff_round=group.cutoff_round)}": group
        for group in artifact.groups
    }
    chosen_label = st.selectbox(
        label="Question / cutoff",
        options=list(group_options.keys()),
        index=0,
        key="probe_similarity_agent_pair_group_picker",
    )
    chosen_group: AgentPairSimGroup = group_options[chosen_label]
    cells_by_pair = {(cell.i, cell.j): cell.value for cell in chosen_group.cells}
    matrix = _matrix_from_cells(cells_by_pair=cells_by_pair, size=len(chosen_group.agent_ids))
    labels = [
        f"{agent_id}<br>({model})"
        for agent_id, model in zip(chosen_group.agent_ids, chosen_group.models, strict=True)
    ]
    fig = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=labels,
            y=labels,
            colorscale=_HEATMAP_COLORSCALE,
            zmin=0.0,
            zmax=1.0,
            text=[[f"{value:.2f}" for value in row] for row in matrix],
            texttemplate="%{text}",
        )
    )
    fig.update_layout(
        title=f"{chosen_group.question_id} / "
        f"{_format_cutoff(cutoff_round=chosen_group.cutoff_round)} "
        f"— mean cross-replica similarity",
        height=460,
        margin=dict(t=60, b=80, l=120, r=40),
    )
    st.plotly_chart(fig, width="stretch")
    st.markdown("**Per-agent responses (one per replica)**")
    response_rows: list[dict[str, str]] = []
    for agent_id in chosen_group.agent_ids:
        for replica_idx, text in enumerate(chosen_group.response_texts_by_agent[agent_id], start=1):
            response_rows.append(
                {
                    "agent": agent_id,
                    "replica": str(replica_idx),
                    "response": _truncate(text=text, limit=200),
                }
            )
    st.dataframe(response_rows, hide_index=True, width="stretch")


def _render_cutoff_trajectory_subview(probe_runs: list[ProbeSimilarityRun]) -> None:
    """Sub-view 4 — within-run cutoff trajectory per (agent, question)."""
    title_col, info_col = st.columns([8, 1])
    with title_col:
        st.markdown("### Cutoff trajectory")
    with info_col:
        with st.popover("ⓘ", help="What this metric measures"):
            st.markdown(
                "**The question this answers:** if you probe the same agent "
                "at multiple snapshots in time (e.g. once with "
                "`--probe-round 5`, once with `--probe-round 10`, once at "
                "end-of-run), does its protocol stabilise across snapshots, "
                "or keep shifting? Captures protocol *stabilisation over "
                "rounds*, complementing self-similarity which only sees one "
                "snapshot.\n\n"
                "**How it's computed:** for every `(agent, question)` pair "
                "where the JSONL has rows tagged with at least 2 distinct "
                "`cutoff_round` values, we sort cutoffs ascending (treating "
                "`null` end-of-run as the latest cutoff) and compute the "
                "mean cross-replica normalized Levenshtein similarity "
                "between every adjacent pair of snapshots. The bar shown "
                "for each run is the macro mean of those adjacent-pair "
                "values.\n\n"
                "**How to read the score** (range 0–1):\n"
                "- `~1.0` — the agent's responses barely change between "
                "adjacent snapshots: the protocol is stable.\n"
                "- `~0.5–0.8` — moderate drift: the protocol is still "
                "evolving between snapshots.\n"
                "- `< 0.3` — large drift: the agent kept changing its "
                "answers across the round window.\n\n"
                "**Generating multi-cutoff data:** rerun the `protocol_probe` "
                "metric with several `--probe-round R` values on the same "
                "run. Each run appends rows tagged with that cutoff to "
                "`protocol_probe_responses.jsonl`. Single-cutoff JSONLs "
                "produce no trajectory."
            )
    runs_with_artifact = [
        run
        for run in probe_runs
        if run.cutoff_trajectory is not None and run.cutoff_trajectory.groups
    ]
    if not runs_with_artifact:
        st.info(
            "None of the selected runs have a cutoff-trajectory artifact "
            "with groups. The metric only fires when the probe JSONL "
            "contains rows from multiple `cutoff_round` values."
        )
        return
    score_by_run_id = {
        run.run_id: run.cutoff_trajectory.overall_mean_similarity
        for run in runs_with_artifact
        if run.cutoff_trajectory is not None
    }
    fig = _comparison_bar_chart(
        title="Overall adjacent-cutoff similarity per run",
        runs=runs_with_artifact,
        score_by_run_id=score_by_run_id,
        yaxis_title="Macro mean similarity",
    )
    st.plotly_chart(fig, width="stretch")
    st.markdown(
        "Each bar is the macro mean of cross-replica similarity between "
        "adjacent cutoff snapshots, averaged across (agent, question) "
        "groups in that run. Higher values indicate the protocol "
        "stabilised across cutoffs; lower values indicate drift."
    )
    st.markdown("---")
    st.markdown("**Drill into one run**")
    chosen = _drill_run_picker(
        label="Run",
        runs=runs_with_artifact,
        state_key="probe_similarity_cutoff_drill_run",
    )
    if chosen.cutoff_trajectory is None:
        return
    artifact = chosen.cutoff_trajectory
    st.markdown(
        f"**Overall mean adjacent-cutoff similarity**: "
        f"`{artifact.overall_mean_similarity:.3f}` across "
        f"`{sum(len(group.pairs) for group in artifact.groups)}` adjacent-cutoff pairs in "
        f"`{len(artifact.groups)}` (agent, question) groups."
    )
    group_options = {f"{group.agent_id} / {group.question_id}": group for group in artifact.groups}
    chosen_label = st.selectbox(
        label="Agent / question",
        options=list(group_options.keys()),
        index=0,
        key="probe_similarity_cutoff_group_picker",
    )
    chosen_group: CutoffTrajectoryGroup = group_options[chosen_label]
    pair_labels = [
        f"{_format_cutoff(cutoff_round=pair.cutoff_a)} → "
        f"{_format_cutoff(cutoff_round=pair.cutoff_b)}"
        for pair in chosen_group.pairs
    ]
    fig = go.Figure(
        data=go.Scatter(
            x=pair_labels,
            y=[pair.mean_similarity for pair in chosen_group.pairs],
            mode="lines+markers",
            marker=dict(size=10),
        )
    )
    fig.update_layout(
        title=f"{chosen_group.agent_id} / {chosen_group.question_id} "
        f"— adjacent-cutoff similarity",
        xaxis_title="Cutoff transition",
        yaxis=dict(title="Mean similarity", range=[0.0, 1.05]),
        height=400,
        margin=dict(t=60, b=80, l=60, r=40),
    )
    st.plotly_chart(fig, width="stretch")


def _render_cross_run_subview(probe_runs: list[ProbeSimilarityRun]) -> None:
    """Sub-view 3 — cross-run model-vs-model live pairwise matrix.

    Live Levenshtein is computed only on the user-selected slice
    (one ``question_id`` × at most a few replicas per model), keeping
    the working set small.
    """
    title_col, info_col = st.columns([8, 1])
    with title_col:
        st.markdown("### Cross-run model-vs-model")
    with info_col:
        with st.popover("ⓘ", help="What this view computes"):
            st.markdown(
                "**The question this answers:** how similar are the "
                "protocols different runs (often different models) "
                "developed for the same probe question? Lets you spot, "
                "e.g., whether opus and sonnet converged on the same code "
                "or two different ones.\n\n"
                "**How it's computed:** unlike the other three sub-views, "
                "this one has no precomputed artifact — it gathers the raw "
                "probe rows from every selected run, filters to one chosen "
                "`question_id` and one chosen role, then computes a live "
                "pairwise normalized Levenshtein matrix between every row "
                "in the slice. Cell `(i, j)` is the similarity between "
                "response `i`'s `response_text` and response `j`'s "
                "`response_text`.\n\n"
                "**How to read the heatmap:**\n"
                "- Bright squares grouped by model → that model is "
                "internally consistent (replicas agree with each other).\n"
                "- Bright cross-model blocks → different runs/models "
                "converged on the same surface form for this question.\n"
                "- Dark cross-model blocks → models picked different ways "
                "of answering the same input.\n\n"
                "**Why live and not cached:** the slice is user-driven "
                "(question × role × models) and small (typically tens of "
                "responses), so the matrix takes ~1 s to compute. Caching "
                "every possible slice across runs would be more work than "
                "computing the relevant one on demand."
            )
    rows_with_runs: list[tuple[str, ProtocolProbeResponse]] = []
    for run in probe_runs:
        for row in run.rows:
            rows_with_runs.append((run.run_id, row))
    if not rows_with_runs:
        st.info("No probe rows are loaded across the selected runs.")
        return
    question_options = sorted({row.question_id for _, row in rows_with_runs})
    chosen_question = st.selectbox(
        label="Probe question",
        options=question_options,
        index=0,
        key="probe_similarity_cross_run_question",
    )
    matching = [
        (run_id, row) for run_id, row in rows_with_runs if row.question_id == chosen_question
    ]
    if not matching:
        st.info("No probe rows match the selected question.")
        return
    role_options = sorted({row.role_name for _, row in matching})
    chosen_role = st.selectbox(
        label="Role",
        options=role_options,
        index=0,
        key="probe_similarity_cross_run_role",
    )
    role_matching = [(run_id, row) for run_id, row in matching if row.role_name == chosen_role]
    model_options = sorted({row.model for _, row in role_matching})
    chosen_models = st.multiselect(
        label="Models to compare",
        options=model_options,
        default=model_options[: min(2, len(model_options))],
        key="probe_similarity_cross_run_models",
    )
    if not chosen_models:
        st.info("Pick at least one model to render the matrix.")
        return
    items = [(run_id, row) for run_id, row in role_matching if row.model in set(chosen_models)]
    if not items:
        st.info("No probe rows match the selected models.")
        return
    items.sort(key=lambda pair: (pair[1].model, pair[0], pair[1].agent_id, pair[1].replica_index))
    labels = [
        f"{row.model}<br>{run_id}<br>{row.agent_id} r{row.replica_index}" for run_id, row in items
    ]
    texts = [row.response_text for _, row in items]
    size = len(texts)
    matrix: list[list[float]] = [[0.0] * size for _ in range(size)]
    for i in range(size):
        matrix[i][i] = 1.0
        for j in range(i + 1, size):
            value = Levenshtein.normalized_similarity(texts[i], texts[j])
            matrix[i][j] = value
            matrix[j][i] = value
    fig = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=labels,
            y=labels,
            colorscale=_HEATMAP_COLORSCALE,
            zmin=0.0,
            zmax=1.0,
        )
    )
    fig.update_layout(
        title=f"{chosen_question} / {chosen_role} — pairwise similarity (live)",
        height=620,
        margin=dict(t=60, b=160, l=160, r=40),
    )
    st.plotly_chart(fig, width="stretch")
    st.markdown("**Responses**")
    response_rows = [
        {
            "model": row.model,
            "run": run_id,
            "agent": row.agent_id,
            "replica": str(row.replica_index),
            "response": _truncate(text=row.response_text, limit=200),
        }
        for run_id, row in items
    ]
    st.dataframe(response_rows, hide_index=True, width="stretch")


def render(evaluated: list[EvaluatedRun]) -> None:
    """Render the four-sub-view Probe similarity tab body."""
    st.markdown(
        "Levenshtein-based comparisons over `protocol_probe_responses.jsonl`. "
        "Three of the four sub-views render artifacts produced by the per-run "
        "similarity metrics; the cross-run sub-view computes its matrix live "
        "on the selected slice."
    )
    probe_runs = list_probe_similarity_runs(evaluated_runs=evaluated)
    if not probe_runs:
        st.info(
            "No runs have probe data or similarity artifacts. Run the "
            "`protocol_probe` metric first, then one or more of "
            "`protocol_probe_replica_self_similarity`, "
            "`protocol_probe_agent_pair_similarity`, "
            "`protocol_probe_cutoff_trajectory`."
        )
        return
    options_by_label = {_run_picker_label(probe_run=run): run for run in probe_runs}
    chosen_labels = st.multiselect(
        label=f"Runs to compare ({len(options_by_label)} available)",
        options=list(options_by_label.keys()),
        default=[],
        key="probe_similarity_runs_multiselect",
        help=(
            "Every sub-view operates on these runs. Nothing is preselected "
            "— pick the runs you want to compare. Within-run sub-views show "
            "one bar per selected run that has the relevant artifact, with "
            "a drill-down picker for the per-question detail. The cross-run "
            "sub-view aggregates raw probe rows across these runs."
        ),
    )
    if not chosen_labels:
        st.info("Pick at least one run to render the sub-views.")
        return
    selected_runs = [options_by_label[label] for label in chosen_labels]
    (
        replica_panel,
        agent_pair_panel,
        cross_run_panel,
        cutoff_panel,
    ) = st.tabs(
        [
            "Replica self-similarity",
            "Agent-pair similarity",
            "Cross-run model-vs-model",
            "Cutoff trajectory",
        ]
    )
    with replica_panel:
        _render_replica_self_subview(probe_runs=selected_runs)
    with agent_pair_panel:
        _render_agent_pair_subview(probe_runs=selected_runs)
    with cross_run_panel:
        _render_cross_run_subview(probe_runs=selected_runs)
    with cutoff_panel:
        _render_cutoff_trajectory_subview(probe_runs=selected_runs)
