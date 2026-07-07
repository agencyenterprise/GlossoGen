"""Load per-run protocol-probe similarity artifacts for the Streamlit tab.

The three veyru similarity metrics
(``protocol_probe_replica_self_similarity``, ``protocol_probe_agent_pair_similarity``,
``protocol_probe_cutoff_trajectory``) each persist a JSON artifact next to the
run's ``protocol_probe_responses.jsonl`` file. This module reads those
artifacts and the raw probe rows, returning a ``ProbeSimilarityRun`` per run
that has at least one of the artifacts. The cross-run "model-vs-model"
sub-view in the tab does its own live pairwise computation on the raw rows
collected here — that is the only Levenshtein work outside of the metrics
themselves.

Per-run reads run concurrently in worker threads via ``asyncio.gather`` +
``asyncio.to_thread`` so a UI listing dozens of runs scales with available
cores instead of summing per-run latency. The module is streamlit-free.
"""

import asyncio
import logging
from pathlib import Path
from typing import NamedTuple

import orjson

from analysis.results_viewer.run_catalog import EvaluatedRun
from glossogen.evaluation.metrics.protocol_probe.protocol_probe_agent_pair_similarity_metric import (  # noqa: E501
    ARTIFACT_FILE_NAME as AGENT_PAIR_ARTIFACT_FILE_NAME,
)
from glossogen.evaluation.metrics.protocol_probe.protocol_probe_agent_pair_similarity_metric import (  # noqa: E501
    AgentPairSimArtifact,
)
from glossogen.evaluation.metrics.protocol_probe.protocol_probe_cutoff_trajectory_metric import (  # noqa: E501
    ARTIFACT_FILE_NAME as CUTOFF_TRAJECTORY_ARTIFACT_FILE_NAME,
)
from glossogen.evaluation.metrics.protocol_probe.protocol_probe_cutoff_trajectory_metric import (  # noqa: E501
    CutoffTrajectoryArtifact,
)
from glossogen.evaluation.metrics.protocol_probe.protocol_probe_replica_self_similarity_metric import (  # noqa: E501
    ARTIFACT_FILE_NAME as REPLICA_SELF_ARTIFACT_FILE_NAME,
)
from glossogen.evaluation.metrics.protocol_probe.protocol_probe_replica_self_similarity_metric import (  # noqa: E501
    ReplicaSelfSimArtifact,
)
from glossogen.evaluation.metrics.protocol_probe.response_models import ProtocolProbeResponse
from glossogen.evaluation.metrics.protocol_probe.similarity_core import (
    ARTIFACT_SCHEMA_VERSION,
    PROBE_RESPONSES_FILE_NAME,
    load_probe_rows,
)

logger = logging.getLogger(__name__)


_PROBE_FILES = (
    PROBE_RESPONSES_FILE_NAME,
    REPLICA_SELF_ARTIFACT_FILE_NAME,
    AGENT_PAIR_ARTIFACT_FILE_NAME,
    CUTOFF_TRAJECTORY_ARTIFACT_FILE_NAME,
    "labels.json",
)


class _ProbeRunCacheKey(NamedTuple):
    """Identity tuple for a run's probe + artifact + labels stats.

    Each element is a ``(size, mtime_ns)`` tuple if the file exists, or
    ``None`` if it doesn't. The order matches :data:`_PROBE_FILES`.
    """

    fingerprints: tuple[tuple[int, int] | None, ...]
    primary_model: str
    round_count: int | None
    round_time_budget_seconds: int | None
    postmortem_enabled: bool


_PROBE_RUN_CACHE: dict[Path, tuple[_ProbeRunCacheKey, "ProbeSimilarityRun"]] = {}


def _probe_run_cache_key(*, evaluated: EvaluatedRun) -> _ProbeRunCacheKey:
    """Stat each probe-related file and combine with the run's stable metadata."""
    fingerprints: list[tuple[int, int] | None] = []
    for filename in _PROBE_FILES:
        path = evaluated.run_dir / filename
        try:
            stat = path.stat()
        except FileNotFoundError:
            fingerprints.append(None)
            continue
        fingerprints.append((stat.st_size, stat.st_mtime_ns))
    raw_round_count = evaluated.metadata.scenario_config.get("round_count")
    if isinstance(raw_round_count, int):
        round_count = raw_round_count
    else:
        round_count = None
    raw_budget = evaluated.metadata.scenario_config.get("round_time_budget_seconds")
    if isinstance(raw_budget, (int, float)):
        round_time_budget_seconds = int(raw_budget)
    else:
        round_time_budget_seconds = None
    return _ProbeRunCacheKey(
        fingerprints=tuple(fingerprints),
        primary_model=evaluated.metadata.primary_model,
        round_count=round_count,
        round_time_budget_seconds=round_time_budget_seconds,
        postmortem_enabled=bool(
            evaluated.metadata.scenario_config.get("postmortem_enabled", False)
        ),
    )


class ProbeSimilarityRun(NamedTuple):
    """One run's loaded probe artifacts + raw rows for the similarity tab.

    Each artifact is optional — runs that only ran one of the three
    metrics still surface in the tab, with the missing sub-view greyed
    out. ``rows`` carries the raw probe responses parsed from the JSONL
    so the tab's cross-run sub-view can compute live pairwise distances
    without re-parsing the file.
    """

    run_id: str
    run_dir: Path
    scenario_name: str
    primary_model: str
    round_count: int | None
    round_time_budget_seconds: int | None
    postmortem_enabled: bool
    labels: list[str]
    rows: list[ProtocolProbeResponse]
    replica_self: ReplicaSelfSimArtifact | None
    agent_pair: AgentPairSimArtifact | None
    cutoff_trajectory: CutoffTrajectoryArtifact | None


def _read_replica_self(run_dir: Path) -> ReplicaSelfSimArtifact | None:
    """Read and validate ``protocol_probe_replica_self_similarity.json``."""
    path = run_dir / REPLICA_SELF_ARTIFACT_FILE_NAME
    if not path.exists():
        return None
    try:
        artifact = ReplicaSelfSimArtifact.model_validate_json(path.read_bytes())
    except Exception:
        logger.exception("Failed to parse replica-self artifact at %s", path)
        return None
    if artifact.schema_version != ARTIFACT_SCHEMA_VERSION:
        logger.warning(
            "Replica-self artifact at %s has schema_version=%d, expected %d; skipping.",
            path,
            artifact.schema_version,
            ARTIFACT_SCHEMA_VERSION,
        )
        return None
    return artifact


def _read_agent_pair(run_dir: Path) -> AgentPairSimArtifact | None:
    """Read and validate ``protocol_probe_agent_pair_similarity.json``."""
    path = run_dir / AGENT_PAIR_ARTIFACT_FILE_NAME
    if not path.exists():
        return None
    try:
        artifact = AgentPairSimArtifact.model_validate_json(path.read_bytes())
    except Exception:
        logger.exception("Failed to parse agent-pair artifact at %s", path)
        return None
    if artifact.schema_version != ARTIFACT_SCHEMA_VERSION:
        logger.warning(
            "Agent-pair artifact at %s has schema_version=%d, expected %d; skipping.",
            path,
            artifact.schema_version,
            ARTIFACT_SCHEMA_VERSION,
        )
        return None
    return artifact


def _read_cutoff_trajectory(run_dir: Path) -> CutoffTrajectoryArtifact | None:
    """Read and validate ``protocol_probe_cutoff_trajectory.json``."""
    path = run_dir / CUTOFF_TRAJECTORY_ARTIFACT_FILE_NAME
    if not path.exists():
        return None
    try:
        artifact = CutoffTrajectoryArtifact.model_validate_json(path.read_bytes())
    except Exception:
        logger.exception("Failed to parse cutoff-trajectory artifact at %s", path)
        return None
    if artifact.schema_version != ARTIFACT_SCHEMA_VERSION:
        logger.warning(
            "Cutoff-trajectory artifact at %s has schema_version=%d, expected %d; skipping.",
            path,
            artifact.schema_version,
            ARTIFACT_SCHEMA_VERSION,
        )
        return None
    return artifact


def _read_labels(run_dir: Path) -> list[str]:
    """Return the labels stored in the run directory's ``labels.json``."""
    labels_path = run_dir / "labels.json"
    if not labels_path.exists():
        return []
    try:
        raw = orjson.loads(labels_path.read_bytes())
    except Exception:
        logger.exception("Failed to read labels at %s", labels_path)
        return []
    if not isinstance(raw, list):
        return []
    return [label for label in raw if isinstance(label, str)]


def _build_run_sync(evaluated: EvaluatedRun) -> ProbeSimilarityRun | None:
    """Synchronous per-run load with stat-based memoization.

    A cached entry is reused whenever every probe-related file's
    ``(size, mtime_ns)`` matches the cached key. On a miss, all four
    files are reparsed and the result is cached. Returns ``None`` for
    runs that have neither a probe JSONL nor any similarity artifact.
    """
    cache_key = _probe_run_cache_key(evaluated=evaluated)
    cached = _PROBE_RUN_CACHE.get(evaluated.run_dir)
    if cached is not None and cached[0] == cache_key:
        return cached[1]
    rows = load_probe_rows(run_dir=evaluated.run_dir)
    replica_self = _read_replica_self(run_dir=evaluated.run_dir)
    agent_pair = _read_agent_pair(run_dir=evaluated.run_dir)
    cutoff_trajectory = _read_cutoff_trajectory(run_dir=evaluated.run_dir)
    if not rows and replica_self is None and agent_pair is None and cutoff_trajectory is None:
        return None
    probe_run = ProbeSimilarityRun(
        run_id=evaluated.run_id,
        run_dir=evaluated.run_dir,
        scenario_name=evaluated.scenario_name,
        primary_model=cache_key.primary_model,
        round_count=cache_key.round_count,
        round_time_budget_seconds=cache_key.round_time_budget_seconds,
        postmortem_enabled=cache_key.postmortem_enabled,
        labels=_read_labels(run_dir=evaluated.run_dir),
        rows=rows,
        replica_self=replica_self,
        agent_pair=agent_pair,
        cutoff_trajectory=cutoff_trajectory,
    )
    _PROBE_RUN_CACHE[evaluated.run_dir] = (cache_key, probe_run)
    return probe_run


async def _build_run_async(evaluated: EvaluatedRun) -> ProbeSimilarityRun | None:
    """Worker-thread wrapper around ``_build_run_sync`` for concurrent fan-out."""
    return await asyncio.to_thread(_build_run_sync, evaluated)


def _has_any_probe_file(run_dir: Path) -> bool:
    """Cheap existence check: return ``True`` if any probe-related file exists."""
    for filename in _PROBE_FILES:
        if filename == "labels.json":
            continue
        if (run_dir / filename).exists():
            return True
    return False


async def _list_probe_similarity_runs_async(
    evaluated_runs: list[EvaluatedRun],
) -> list[ProbeSimilarityRun]:
    """Concurrent fan-out across candidate runs, returning successful loads.

    A cheap synchronous pre-filter drops runs that have no probe-related
    files at all — typical large corpora have hundreds of evaluated runs
    but only a few with probe data, and skipping the thread-pool dispatch
    for those keeps warm-cache renders close to zero overhead.
    """
    candidates = [run for run in evaluated_runs if _has_any_probe_file(run_dir=run.run_dir)]
    if not candidates:
        return []
    results = await asyncio.gather(
        *(_build_run_async(evaluated=run) for run in candidates),
        return_exceptions=True,
    )
    out: list[ProbeSimilarityRun] = []
    for source_run, result in zip(candidates, results, strict=True):
        if isinstance(result, BaseException):
            logger.exception(
                "Failed to build probe-similarity run for %s",
                source_run.run_id,
                exc_info=result,
            )
            continue
        if isinstance(result, ProbeSimilarityRun):
            out.append(result)
    return out


def list_probe_similarity_runs(
    evaluated_runs: list[EvaluatedRun],
) -> list[ProbeSimilarityRun]:
    """Filter ``evaluated_runs`` to those with at least one probe-similarity artifact.

    Per-run loads run concurrently in worker threads. The returned list
    preserves the input order of runs that have any of the three
    artifacts (or raw probe rows that the cross-run sub-view can use).
    """
    return asyncio.run(_list_probe_similarity_runs_async(evaluated_runs=evaluated_runs))
