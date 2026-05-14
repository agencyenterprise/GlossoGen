"""Within-run replica self-similarity over protocol-probe responses.

For each ``(agent_id, question_id, cutoff_round)`` triple in
``protocol_probe_responses.jsonl`` with at least two replicas, this metric
computes the pairwise normalized Levenshtein similarity matrix across that
agent's replica responses on that question. The headline ``score`` is the
macro mean of those per-group means (mean of means, so groups with more
replicas don't dominate). The full per-group matrices are persisted to
``protocol_probe_replica_self_similarity.json`` inside the run directory
for the streamlit "Probe similarity" tab to render heatmaps from.

A score near ``1.0`` is the expected signal for a converged protocol where
the agent's surface form is deterministic — e.g. all replicas emit the same
short code like ``!AC``. The interesting variation lives at earlier
``cutoff_round`` snapshots (taken with ``--probe-round R`` before the
protocol stabilised) and across agents/models.
"""

import logging
from pathlib import Path
from typing import NamedTuple

import orjson
from pydantic import BaseModel

from schmidt.evaluation.metric_core.measurement import AgentObservation, Measurement
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.evaluation.metrics.protocol_probe.response_models import ProtocolProbeResponse
from schmidt.evaluation.metrics.protocol_probe.similarity_core import (
    ARTIFACT_SCHEMA_VERSION,
    ProbeSimilarityCell,
    cutoff_sort_key,
    load_probe_rows,
    matrix_to_cells,
    pairwise_similarity_matrix,
    upper_triangle_mean,
)
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

ARTIFACT_FILE_NAME = "protocol_probe_replica_self_similarity.json"


class ReplicaSelfSimGroup(BaseModel):
    """One ``(agent_id, question_id, cutoff_round)`` group's stored result.

    ``replica_indices`` and ``response_texts`` align with the matrix axes
    so the streamlit tab can label rows / columns and surface raw text on
    hover. ``cells`` stores only the strict-upper-triangle of the matrix
    (``i < j``); the diagonal is implicitly ``1.0``.
    """

    agent_id: str
    role_name: str
    model: str
    provider: str
    question_id: str
    question_role_filter: str
    cutoff_round: int | None
    replica_indices: list[int]
    response_texts: list[str]
    cells: list[ProbeSimilarityCell]
    mean_similarity: float


class ReplicaSelfSimArtifact(BaseModel):
    """On-disk artifact written by ``ProtocolProbeReplicaSelfSimilarityMetric``.

    The streamlit data layer reads this file directly and skips runs whose
    ``schema_version`` does not match the current expected version.
    """

    schema_version: int
    groups: list[ReplicaSelfSimGroup]
    overall_mean_similarity: float


class _GroupKey(NamedTuple):
    """Hashable key for grouping rows in a single pass."""

    agent_id: str
    question_id: str
    cutoff_round: int | None


def _group_rows(rows: list[ProtocolProbeResponse]) -> dict[_GroupKey, list[ProtocolProbeResponse]]:
    """Bucket probe rows by ``(agent_id, question_id, cutoff_round)`` preserving input order."""
    groups: dict[_GroupKey, list[ProtocolProbeResponse]] = {}
    for row in rows:
        key = _GroupKey(
            agent_id=row.agent_id,
            question_id=row.question_id,
            cutoff_round=row.cutoff_round,
        )
        groups.setdefault(key, []).append(row)
    return groups


def _build_group(
    rows: list[ProtocolProbeResponse],
) -> ReplicaSelfSimGroup | None:
    """Compute the matrix for one group; returns ``None`` for groups with <2 replicas."""
    if len(rows) < 2:
        return None
    sorted_rows = sorted(rows, key=lambda row: row.replica_index)
    response_texts = [row.response_text for row in sorted_rows]
    matrix = pairwise_similarity_matrix(strings=response_texts)
    head = sorted_rows[0]
    return ReplicaSelfSimGroup(
        agent_id=head.agent_id,
        role_name=head.role_name,
        model=head.model,
        provider=head.provider,
        question_id=head.question_id,
        question_role_filter=head.question_role_filter,
        cutoff_round=head.cutoff_round,
        replica_indices=[row.replica_index for row in sorted_rows],
        response_texts=response_texts,
        cells=matrix_to_cells(matrix=matrix),
        mean_similarity=upper_triangle_mean(matrix=matrix),
    )


def _write_artifact(run_dir: Path, artifact: ReplicaSelfSimArtifact) -> None:
    """Persist the artifact JSON next to the probe responses JSONL."""
    path = run_dir / ARTIFACT_FILE_NAME
    path.write_bytes(orjson.dumps(artifact.model_dump(mode="json")))


def _agents_per_observation(groups: list[ReplicaSelfSimGroup]) -> list[AgentObservation]:
    """Collapse groups to one ``AgentObservation`` per agent (mean over their groups)."""
    by_agent: dict[str, list[float]] = {}
    role_by_agent: dict[str, str] = {}
    for group in groups:
        by_agent.setdefault(group.agent_id, []).append(group.mean_similarity)
        role_by_agent[group.agent_id] = group.role_name
    return [
        AgentObservation(
            agent_id=agent_id,
            value=sum(values) / len(values),
            note=(
                f"role={role_by_agent[agent_id]}; mean self-similarity over "
                f"{len(values)} (question, cutoff) groups."
            ),
        )
        for agent_id, values in sorted(by_agent.items())
    ]


class ProtocolProbeReplicaSelfSimilarityMetric(Metric):
    """Mean within-replica response similarity across all probe groups."""

    name = "protocol_probe_replica_self_similarity"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score replica self-similarity, write the artifact, return one Measurement."""
        _ = events, agent_configs, scenario, llm_provider, options
        rows = load_probe_rows(run_dir=run_dir)
        if not rows:
            logger.info(
                "%s: skipping — protocol_probe_responses.jsonl missing or empty",
                self.name,
            )
            return []
        rows_by_key = _group_rows(rows=rows)
        sorted_keys = sorted(
            rows_by_key.keys(),
            key=lambda key: (key.agent_id, key.question_id, cutoff_sort_key(key.cutoff_round)),
        )
        groups: list[ReplicaSelfSimGroup] = []
        for key in sorted_keys:
            built = _build_group(rows=rows_by_key[key])
            if built is not None:
                groups.append(built)
        if not groups:
            logger.info(
                "%s: skipping — no (agent, question, cutoff) group has ≥2 replicas",
                self.name,
            )
            return []
        overall = sum(group.mean_similarity for group in groups) / len(groups)
        artifact = ReplicaSelfSimArtifact(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            groups=groups,
            overall_mean_similarity=overall,
        )
        _write_artifact(run_dir=run_dir, artifact=artifact)
        summary = (
            f"Replica self-similarity (macro mean across {len(groups)} groups): "
            f"{overall:.3f}. Saturation at 1.0 is expected on converged protocols."
        )
        return [
            Measurement(
                metric_name=self.name,
                score=overall,
                score_unit="similarity",
                summary=summary,
                per_round=[],
                per_agent=_agents_per_observation(groups=groups),
            )
        ]
