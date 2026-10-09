"""Per-message redundancy factors, read back from the `language_repetition` sidecar.

The metric writes one JSONL row per judged message keyed by `message_id`, and its
Measurement carries only the per-round mean. The per-message number is the finer
observation, so the message table joins it back on that id.

A run that never ran the metric has no sidecar, and a message the judge did not
score has no row. Both leave the cell empty, on the same rule the metric columns
follow: no number exists, and it is not zero.
"""

import logging
from pathlib import Path

from pydantic import ValidationError

from glossogen.evaluation.metrics.language_repetition_sidecar import (
    LANGUAGE_REPETITION_SIDECAR_FILENAME,
    MessageRepetitionRow,
)

logger = logging.getLogger(__name__)


def read_repetition_by_message_id(run_dir: Path) -> dict[str, float]:
    """Return ``message_id -> repetition_factor``, empty when the run has no sidecar.

    A row that does not parse is skipped, so it costs that message its factor and
    no other.
    """
    path = run_dir / LANGUAGE_REPETITION_SIDECAR_FILENAME
    if not path.is_file():
        return {}
    try:
        lines = path.read_bytes().splitlines()
    except OSError:
        logger.exception(
            "Could not read %s; exporting those messages without a repetition factor", path
        )
        return {}
    factors: dict[str, float] = {}
    for line in lines:
        if not line.strip():
            continue
        try:
            row = MessageRepetitionRow.model_validate_json(line)
        except ValidationError:
            logger.exception("Skipping a malformed row in %s", path)
            continue
        factors[row.message_id] = row.repetition_factor
    return factors
