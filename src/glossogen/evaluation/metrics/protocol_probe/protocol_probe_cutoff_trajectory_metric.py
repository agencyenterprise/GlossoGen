"""Cross-cutoff trajectory of protocol-probe responses.

When ``glossogen evaluate ... --metrics protocol_probe`` is run multiple
times against the same run with different ``--probe-round`` values (and
possibly with no ``--probe-round`` for the full end-of-run snapshot), the
resulting JSONL contains rows tagged with several distinct
``cutoff_round`` values for the same agent on the same question. This
metric measures how similar an agent's responses are between adjacent
cutoff snapshots — a proxy for "did the protocol stabilise across these
rounds, or did it keep drifting?".

For each ``(agent_id, question_id)`` pair with at least two distinct
``cutoff_round`` values, the metric:

1. Sorts cutoff values ascending, treating ``None`` (end-of-run) as the
   latest cutoff.
2. For every adjacent pair of cutoffs, computes the mean cross-replica
   similarity between the two snapshots' responses.
3. Records all of these adjacent-pair similarities in the artifact.

The headline ``score`` is the macro mean across every recorded adjacent
pair (mean of pair means). A score near ``1.0`` means responses are
stable across cutoffs; a low score means the agent's surface form kept
shifting between snapshots. Runs whose probe JSONL contains only a
single ``cutoff_round`` value emit a zero-score Measurement explaining
the metric does not apply.
"""

import logging
from pathlib import Path
from typing import NamedTuple

import orjson
from pydantic import BaseModel
from rapidfuzz.distance import Levenshtein

from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metrics.protocol_probe.response_models import ProtocolProbeResponse
from glossogen.evaluation.metrics.protocol_probe.similarity_core import (
    ARTIFACT_SCHEMA_VERSION,
    load_probe_rows,
)
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

ARTIFACT_FILE_NAME = "protocol_probe_cutoff_trajectory.json"


class CutoffPair(BaseModel):
    """Mean similarity between two adjacent cutoff snapshots for one (agent, question)."""

    cutoff_a: int | None
    cutoff_b: int | None
    response_texts_a: list[str]
    response_texts_b: list[str]
    mean_similarity: float


class CutoffTrajectoryGroup(BaseModel):
    """One agent's trajectory across cutoffs for a single probe question."""

    agent_id: str
    role_name: str
    model: str
    provider: str
    question_id: str
    question_role_filter: str
    cutoffs: list[int | None]
    pairs: list[CutoffPair]
    mean_similarity: float


class CutoffTrajectoryArtifact(BaseModel):
    """On-disk artifact written by ``ProtocolProbeCutoffTrajectoryMetric``."""

    schema_version: int
    groups: list[CutoffTrajectoryGroup]
    overall_mean_similarity: float


class _GroupKey(NamedTuple):
    """Hashable key for grouping rows by ``(agent_id, question_id)``."""

    agent_id: str
    question_id: str


def _group_rows(
    rows: list[ProtocolProbeResponse],
) -> dict[_GroupKey, dict[int | None, list[ProtocolProbeResponse]]]:
    """Bucket rows by ``(agent_id, question_id)`` then by ``cutoff_round``."""
    groups: dict[_GroupKey, dict[int | None, list[ProtocolProbeResponse]]] = {}
    for row in rows:
        key = _GroupKey(agent_id=row.agent_id, question_id=row.question_id)
        per_cutoff = groups.setdefault(key, {})
        per_cutoff.setdefault(row.cutoff_round, []).append(row)
    return groups


def _sort_cutoffs(cutoffs: list[int | None]) -> list[int | None]:
    """Sort numeric cutoffs ascending; ``None`` (end-of-run) comes last."""
    numeric = sorted(value for value in cutoffs if value is not None)
    has_none = any(value is None for value in cutoffs)
    if has_none:
        return [*numeric, None]
    return list(numeric)


def _mean_cross_replica_similarity(texts_a: list[str], texts_b: list[str]) -> float:
    """Mean Levenshtein similarity over the cartesian product of two replica sets."""
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
    rows_by_cutoff: dict[int | None, list[ProtocolProbeResponse]],
) -> CutoffTrajectoryGroup | None:
    """Compute the adjacent-cutoff similarity series for one (agent, question) group."""
    if len(rows_by_cutoff) < 2:
        return None
    sorted_cutoffs = _sort_cutoffs(cutoffs=list(rows_by_cutoff.keys()))
    head_row = rows_by_cutoff[sorted_cutoffs[0]][0]
    pairs: list[CutoffPair] = []
    for cutoff_a, cutoff_b in zip(sorted_cutoffs, sorted_cutoffs[1:], strict=False):
        rows_a = sorted(rows_by_cutoff[cutoff_a], key=lambda row: row.replica_index)
        rows_b = sorted(rows_by_cutoff[cutoff_b], key=lambda row: row.replica_index)
        texts_a = [row.response_text for row in rows_a]
        texts_b = [row.response_text for row in rows_b]
        pairs.append(
            CutoffPair(
                cutoff_a=cutoff_a,
                cutoff_b=cutoff_b,
                response_texts_a=texts_a,
                response_texts_b=texts_b,
                mean_similarity=_mean_cross_replica_similarity(
                    texts_a=texts_a,
                    texts_b=texts_b,
                ),
            )
        )
    if not pairs:
        return None
    mean_similarity = sum(pair.mean_similarity for pair in pairs) / len(pairs)
    return CutoffTrajectoryGroup(
        agent_id=key.agent_id,
        role_name=head_row.role_name,
        model=head_row.model,
        provider=head_row.provider,
        question_id=key.question_id,
        question_role_filter=head_row.question_role_filter,
        cutoffs=sorted_cutoffs,
        pairs=pairs,
        mean_similarity=mean_similarity,
    )


def _write_artifact(run_dir: Path, artifact: CutoffTrajectoryArtifact) -> None:
    """Persist the artifact JSON next to the probe responses JSONL."""
    path = run_dir / ARTIFACT_FILE_NAME
    path.write_bytes(orjson.dumps(artifact.model_dump(mode="json")))


class ProtocolProbeCutoffTrajectoryMetric(Metric):
    """Mean cross-cutoff response similarity across (agent, question) groups."""

    name = "protocol_probe_cutoff_trajectory"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score cutoff trajectory, write the artifact, return one Measurement."""
        _ = events, agent_configs, scenario, llm_provider, options
        rows = load_probe_rows(run_dir=run_dir)
        if not rows:
            logger.info(
                "%s: skipping — protocol_probe_responses.jsonl missing or empty",
                self.name,
            )
            return []
        grouped = _group_rows(rows=rows)
        groups: list[CutoffTrajectoryGroup] = []
        for key in sorted(grouped.keys()):
            built = _build_group(key=key, rows_by_cutoff=grouped[key])
            if built is not None:
                groups.append(built)
        if not groups:
            logger.info(
                "%s: skipping — probe JSONL contains only one cutoff_round value",
                self.name,
            )
            return []
        all_pair_means = [pair.mean_similarity for group in groups for pair in group.pairs]
        overall = sum(all_pair_means) / len(all_pair_means) if all_pair_means else 0.0
        artifact = CutoffTrajectoryArtifact(
            schema_version=ARTIFACT_SCHEMA_VERSION,
            groups=groups,
            overall_mean_similarity=overall,
        )
        _write_artifact(run_dir=run_dir, artifact=artifact)
        summary = (
            f"Cutoff trajectory similarity (macro mean across "
            f"{len(all_pair_means)} adjacent-cutoff pairs in "
            f"{len(groups)} (agent, question) groups): {overall:.3f}."
        )
        return [
            Measurement(
                metric_name=self.name,
                score=overall,
                score_unit="similarity",
                summary=summary,
                per_round=_per_round_observations(groups=groups),
                per_agent=[],
            )
        ]


def _per_round_observations(groups: list[CutoffTrajectoryGroup]) -> list[RoundObservation]:
    """Aggregate adjacent-pair means into one ``RoundObservation`` per cutoff_b round.

    Numeric ``cutoff_b`` values map to round numbers; pairs ending at
    ``None`` (end-of-run) are folded into a synthetic round number that
    is one past the largest numeric cutoff so the trajectory stays
    plottable on a numeric axis.
    """
    sums_by_round: dict[int, float] = {}
    counts_by_round: dict[int, int] = {}
    end_round_marker: int | None = None
    for group in groups:
        for pair in group.pairs:
            if pair.cutoff_b is not None:
                sums_by_round[pair.cutoff_b] = sums_by_round.get(pair.cutoff_b, 0.0) + (
                    pair.mean_similarity
                )
                counts_by_round[pair.cutoff_b] = counts_by_round.get(pair.cutoff_b, 0) + 1
    numeric_rounds = list(sums_by_round.keys())
    if numeric_rounds:
        end_round_marker = max(numeric_rounds) + 1
    for group in groups:
        for pair in group.pairs:
            if pair.cutoff_b is None and end_round_marker is not None:
                sums_by_round[end_round_marker] = sums_by_round.get(end_round_marker, 0.0) + (
                    pair.mean_similarity
                )
                counts_by_round[end_round_marker] = counts_by_round.get(end_round_marker, 0) + 1
    return [
        RoundObservation(
            round_number=round_number,
            value=sums_by_round[round_number] / counts_by_round[round_number],
            note=(
                f"Mean adjacent-cutoff similarity over "
                f"{counts_by_round[round_number]} (agent, question) groups."
            ),
        )
        for round_number in sorted(sums_by_round.keys())
    ]
