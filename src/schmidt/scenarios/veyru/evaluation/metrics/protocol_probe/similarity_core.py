"""Shared helpers for the three protocol-probe similarity metrics.

The replica-self-similarity, agent-pair-similarity, and cutoff-trajectory
metrics all start from the same ``protocol_probe_responses.jsonl`` file and
all compute pairwise normalized Levenshtein similarity on ``response_text``.
This module centralises:

* JSONL loading (``load_probe_rows``).
* Role-filter to role-name mapping (``ROLE_FILTER_TO_ROLE_NAMES``), shared
  with ``protocol_probe_metric.py`` so question role filters map to the
  same agent set used at probe time.
* The pairwise similarity primitive (``pairwise_similarity_matrix``) on top
  of ``rapidfuzz.distance.Levenshtein.normalized_similarity``.
* Pydantic artifact-row models reused across the three metrics
  (``ProbeSimilarityCell`` etc.) plus the shared schema-version constant.
"""

import logging
from pathlib import Path

from pydantic import BaseModel
from rapidfuzz.distance import Levenshtein

from schmidt.scenarios.veyru.evaluation.metrics.protocol_probe.response_models import (
    ProtocolProbeResponse,
)
from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_A_ROLE,
    FIELD_OBSERVER_B_ROLE,
    FIELD_OBSERVER_ROLE,
    STABILIZATION_ENGINEER_A_ROLE,
    STABILIZATION_ENGINEER_B_ROLE,
    STABILIZATION_ENGINEER_ROLE,
)

logger = logging.getLogger(__name__)

PROBE_RESPONSES_FILE_NAME = "protocol_probe_responses.jsonl"
ARTIFACT_SCHEMA_VERSION = 1

ROLE_FILTER_TO_ROLE_NAMES: dict[str, frozenset[str]] = {
    "field_observer": frozenset(
        {FIELD_OBSERVER_ROLE, FIELD_OBSERVER_A_ROLE, FIELD_OBSERVER_B_ROLE}
    ),
    "stabilization_engineer": frozenset(
        {
            STABILIZATION_ENGINEER_ROLE,
            STABILIZATION_ENGINEER_A_ROLE,
            STABILIZATION_ENGINEER_B_ROLE,
        }
    ),
}


class ProbeSimilarityCell(BaseModel):
    """One pairwise similarity cell stored in a metric artifact.

    ``i`` and ``j`` are zero-based indices into the artifact's labels list
    for that group; ``value`` is the normalized Levenshtein similarity in
    ``[0, 1]``. Symmetric pairs are stored once (i < j); diagonal cells
    are not stored.
    """

    i: int
    j: int
    value: float


def load_probe_rows(run_dir: Path) -> list[ProtocolProbeResponse]:
    """Read every row of ``protocol_probe_responses.jsonl`` for the run.

    Returns an empty list when the file is absent. One ``ProtocolProbeResponse``
    instance per non-empty line; malformed lines are skipped with a warning
    so a partial JSONL does not break evaluation.
    """
    path = probe_responses_path(run_dir=run_dir)
    if not path.exists():
        return []
    rows: list[ProtocolProbeResponse] = []
    with path.open(mode="r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                rows.append(ProtocolProbeResponse.model_validate_json(stripped))
            except Exception:
                logger.exception("Skipping malformed probe row at %s:%d", path, line_number)
    return rows


def probe_responses_path(run_dir: Path) -> Path:
    """Path to the probe responses JSONL inside ``run_dir``."""
    return run_dir / PROBE_RESPONSES_FILE_NAME


def pairwise_similarity_matrix(strings: list[str]) -> list[list[float]]:
    """Compute the symmetric N×N normalized-Levenshtein similarity matrix.

    Diagonal entries are 1.0; off-diagonal entries are
    ``Levenshtein.normalized_similarity(s_i, s_j)`` in ``[0, 1]``. Linear in
    pair count; the caller is responsible for keeping each call's N small
    enough to be reasonable.
    """
    size = len(strings)
    matrix: list[list[float]] = [[0.0] * size for _ in range(size)]
    for i in range(size):
        matrix[i][i] = 1.0
        for j in range(i + 1, size):
            value = Levenshtein.normalized_similarity(strings[i], strings[j])
            matrix[i][j] = value
            matrix[j][i] = value
    return matrix


def upper_triangle_mean(matrix: list[list[float]]) -> float:
    """Mean of the strict-upper-triangle (i < j) cells of a square matrix.

    Returns ``0.0`` when the matrix has fewer than 2 rows (no pairs).
    """
    size = len(matrix)
    if size < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(size):
        for j in range(i + 1, size):
            total += matrix[i][j]
            count += 1
    if count == 0:
        return 0.0
    return total / count


def matrix_to_cells(matrix: list[list[float]]) -> list[ProbeSimilarityCell]:
    """Flatten the strict-upper-triangle of ``matrix`` into ``ProbeSimilarityCell`` rows."""
    cells: list[ProbeSimilarityCell] = []
    size = len(matrix)
    for i in range(size):
        for j in range(i + 1, size):
            cells.append(ProbeSimilarityCell(i=i, j=j, value=matrix[i][j]))
    return cells


def cutoff_sort_key(cutoff_round: int | None) -> tuple[int, int]:
    """Return a tuple sort key that orders numeric cutoffs ascending then ``None`` last.

    Use as the ``cutoff_round`` field of a composite sort key so JSONLs
    that mix numeric ``--probe-round`` values with the default ``null``
    end-of-run probe sort cleanly. Plain ``sorted`` on a tuple with a
    ``cutoff_round: int | None`` field raises ``TypeError`` when both
    flavours are present.
    """
    if cutoff_round is None:
        return (1, 0)
    return (0, cutoff_round)
