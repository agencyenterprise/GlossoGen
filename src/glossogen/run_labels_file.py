"""Reading a run's ``labels.json``, the file that holds the run's labels.

The file is a JSON array of strings. Anything else (a missing file, bytes that are
not JSON, a JSON value that is not a list of strings) is treated as no readable
labels, so every reader agrees on what a hand-edited or truncated file means.
``load_run_labels`` returns ``None`` for such a file, which is what lets
``push-to-prod`` skip the run; ``read_run_labels`` returns ``[]``, which is what the
server and the label mirror show.
"""

import logging
from pathlib import Path
from typing import cast

import orjson

logger = logging.getLogger(__name__)

RUN_LABELS_FILENAME = "labels.json"


def load_run_labels(run_dir: Path) -> list[str] | None:
    """Return the labels in ``run_dir``'s ``labels.json``; ``None`` if it is missing or invalid."""
    labels_path = run_dir / RUN_LABELS_FILENAME
    if not labels_path.exists():
        return None
    try:
        raw = orjson.loads(labels_path.read_bytes())
    except (orjson.JSONDecodeError, OSError):
        logger.exception("Failed to read labels from %s", labels_path)
        return None
    if not isinstance(raw, list):
        logger.warning("Ignoring %s: it holds a %s, not a list", labels_path, type(raw).__name__)
        return None
    labels: list[str] = []
    for value in cast(list[object], raw):
        if not isinstance(value, str):
            logger.warning("Ignoring %s: it holds a non-string label %r", labels_path, value)
            return None
        labels.append(value)
    return labels


def read_run_labels(run_dir: Path) -> list[str]:
    """Return the labels in ``run_dir``'s ``labels.json``; ``[]`` if it is missing or invalid."""
    labels = load_run_labels(run_dir=run_dir)
    if labels is None:
        return []
    return labels
