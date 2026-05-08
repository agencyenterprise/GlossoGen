"""Within-run cross-agent similarity over protocol-probe responses.

For each ``(question_id, cutoff_round)`` triple where two or more agents
share the same role filter (only meaningful in two-team / cross-team
runs), this metric computes the mean cross-replica normalized Levenshtein
similarity between every pair of agents on that probe question. The
headline ``score`` is the macro mean across groups; the full per-group
agent×agent matrices are persisted to
``protocol_probe_agent_pair_similarity.json`` for the streamlit tab.

A score near ``1.0`` means the two teams (or the two agent instances of
the same role in a cross-team setup) converged to nearly identical surface
forms. Scores well below ``1.0`` indicate the teams developed divergent
protocols.

Single-team runs (where only one agent matches each role filter) emit a
zero-score Measurement explaining the metric does not apply.
"""

import logging
from itertools import combinations
from pathlib import Path
from typing import NamedTuple

import orjson
from pydantic import BaseModel
from rapidfuzz.distance import Levenshtein

from schmidt.evaluation.measurement import Measurement
from schmidt.evaluation.metric_protocol import Metric
from schmidt.evaluation.metric_run_options import MetricRunOptions
from schmidt.evaluation.protocol_probe_response import ProtocolProbeResponse
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import SimulationEvent
from schmidt.scenario_protocol import SimulationScenario
from schmidt.scenarios.veyru.evaluation.protocol_probe_similarity_core import (
    ARTIFACT_SCHEMA_VERSION,
    ProbeSimilarityCell,
    cutoff_sort_key,
    load_probe_rows,
)

logger = logging.getLogger(__name__)

ARTIFACT_FILE_NAME = "protocol_probe_agent_pair_similarity.json"


class AgentPairSimGroup(BaseModel):
    """One ``(question_id, cutoff_round)`` group's stored agent-pair matrix.

    ``agent_ids`` is sorted; ``response_texts_by_agent`` carries the raw
    replica texts so the streamlit tab can render hover content. ``cells``
    stores the strict-upper-triangle (i < j) of the agent×agent matrix
    where each cell is the mean cross-replica similarity between two
    agents on this probe question.
    """

    question_id: str
    question_role_filter: str
    cutoff_round: int | None
    agent_ids: list[str]
    role_names: list[str]
    models: list[str]
    response_texts_by_agent: dict[str, list[str]]
    cells: list[ProbeSimilarityCell]
    mean_similarity: float


class AgentPairSimArtifact(BaseModel):
    """On-disk artifact written by ``ProtocolProbeAgentPairSimilarityMetric``."""

    schema_version: int
    groups: list[AgentPairSimGroup]
    overall_mean_similarity: float


class _GroupKey(NamedTuple):
    """Hashable key for grouping rows by ``(question_id, cutoff_round, role_filter)``."""

    question_id: str
    cutoff_round: int | None
    role_filter: str


def _group_rows(
    rows: list[ProtocolProbeResponse],
) -> dict[_GroupKey, dict[str, list[ProtocolProbeResponse]]]:
    """Bucket rows by ``(question_id, cutoff_round, role_filter)`` then by ``agent_id``."""
    groups: dict[_GroupKey, dict[str, list[ProtocolProbeResponse]]] = {}
    for row in rows:
        key = _GroupKey(
            question_id=row.question_id,
            cutoff_round=row.cutoff_round,
            role_filter=row.question_role_filter,
        )
        per_agent = groups.setdefault(key, {})
        per_agent.setdefault(row.agent_id, []).append(row)
    return groups


def _mean_cross_replica_similarity(texts_a: list[str], texts_b: list[str]) -> float:
    """Mean Levenshtein similarity over every (a, b) pair in the cartesian product."""
    if not texts_a or not texts_b:
        return 0.0
    total = 0.0
    count = 0
    for text_a in texts_a:
        for text_b in texts_b:
            total += Levenshtein.normalized_similarity(text_a, text_b)
            count += 1
    return total / count if count > 0 else 0.0


def _build_group(
    key: _GroupKey,
    rows_by_agent: dict[str, list[ProtocolProbeResponse]],
) -> AgentPairSimGroup | None:
    """Compute the agent×agent mean-similarity matrix for one group.

    Returns ``None`` when fewer than two agents matched the role filter
    for this (question, cutoff) — single-team runs and incomplete probe
    passes.
    """
    if len(rows_by_agent) < 2:
        return None
    sorted_agent_ids = sorted(rows_by_agent.keys())
    role_names = [rows_by_agent[agent_id][0].role_name for agent_id in sorted_agent_ids]
    models = [rows_by_agent[agent_id][0].model for agent_id in sorted_agent_ids]
    response_texts_by_agent: dict[str, list[str]] = {}
    for agent_id in sorted_agent_ids:
        agent_rows = sorted(rows_by_agent[agent_id], key=lambda row: row.replica_index)
        response_texts_by_agent[agent_id] = [row.response_text for row in agent_rows]
    cells: list[ProbeSimilarityCell] = []
    pair_means: list[float] = []
    for i, j in combinations(range(len(sorted_agent_ids)), 2):
        value = _mean_cross_replica_similarity(
            texts_a=response_texts_by_agent[sorted_agent_ids[i]],
            texts_b=response_texts_by_agent[sorted_agent_ids[j]],
        )
        cells.append(ProbeSimilarityCell(i=i, j=j, value=value))
        pair_means.append(value)
    mean_similarity = sum(pair_means) / len(pair_means) if pair_means else 0.0
    return AgentPairSimGroup(
        question_id=key.question_id,
        question_role_filter=key.role_filter,
        cutoff_round=key.cutoff_round,
        agent_ids=sorted_agent_ids,
        role_names=role_names,
        models=models,
        response_texts_by_agent=response_texts_by_agent,
        cells=cells,
        mean_similarity=mean_similarity,
    )


def _write_artifact(run_dir: Path, artifact: AgentPairSimArtifact) -> None:
    """Persist the artifact JSON next to the probe responses JSONL."""
    path = run_dir / ARTIFACT_FILE_NAME
    path.write_bytes(orjson.dumps(artifact.model_dump(mode="json")))


class ProtocolProbeAgentPairSimilarityMetric(Metric):
    """Mean cross-agent response similarity across all (question, cutoff) groups."""

    name = "protocol_probe_agent_pair_similarity"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score agent-pair similarity, write the artifact, return one Measurement."""
        _ = events, agent_configs, scenario, llm_provider, options
        rows = load_probe_rows(run_dir=run_dir)
        if not rows:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="similarity",
                    summary=(
                        "protocol_probe_responses.jsonl missing or empty; run "
                        "schmidt evaluate ... --metrics protocol_probe first."
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]
        grouped = _group_rows(rows=rows)
        sorted_keys = sorted(
            grouped.keys(),
            key=lambda key: (
                key.question_id,
                cutoff_sort_key(key.cutoff_round),
                key.role_filter,
            ),
        )
        groups: list[AgentPairSimGroup] = []
        for key in sorted_keys:
            built = _build_group(key=key, rows_by_agent=grouped[key])
            if built is not None:
                groups.append(built)
        if not groups:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="similarity",
                    summary=(
                        "No (question, cutoff) group has ≥ 2 agents matching its "
                        "role filter; this is a single-team run, agent-pair "
                        "similarity does not apply."
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]
        overall = sum(group.mean_similarity for group in groups) / len(groups)
        artifact = AgentPairSimArtifact(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            groups=groups,
            overall_mean_similarity=overall,
        )
        _write_artifact(run_dir=run_dir, artifact=artifact)
        summary = (
            f"Agent-pair similarity (macro mean across {len(groups)} (question, cutoff) "
            f"groups): {overall:.3f}. Lower values indicate the agents' protocols diverged."
        )
        return [
            Measurement(
                metric_name=self.name,
                score=overall,
                score_unit="similarity",
                summary=summary,
                per_round=[],
                per_agent=[],
            )
        ]
