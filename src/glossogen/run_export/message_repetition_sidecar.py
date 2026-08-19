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
from typing import Any, cast

import orjson

SIDECAR_FILENAME = "language_repetition_messages.jsonl"

logger = logging.getLogger(__name__)


def read_repetition_by_message_id(run_dir: Path) -> dict[str, float]:
    """Return ``message_id -> repetition_factor``, empty when the run has no sidecar."""
    path = run_dir / SIDECAR_FILENAME
    if not path.is_file():
        return {}
    factors: dict[str, float] = {}
    try:
        for line in path.read_bytes().splitlines():
            if not line.strip():
                continue
            parsed = orjson.loads(line)
            if not isinstance(parsed, dict):
                continue
            row = cast(dict[str, Any], parsed)
            message_id = row.get("message_id")
            factor = row.get("repetition_factor")
            if not isinstance(message_id, str):
                continue
            if not isinstance(factor, (int, float)):
                continue
            factors[message_id] = float(factor)
    except Exception:
        logger.exception(
            "Could not read %s; exporting those messages without a repetition factor", path
        )
        return {}
    return factors
