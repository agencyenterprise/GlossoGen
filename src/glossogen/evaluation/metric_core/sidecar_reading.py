"""Reading a metric's sidecar file without letting one bad file fail a sweep.

Sidecars are read across whole cohorts: a few thousand runs, written over months by
successive versions of a metric. Some will be truncated by a crashed evaluation, some
written before a field existed. Any of those must cost one run's numbers, not the
selection's.

So every reader here answers with what it could parse and logs what it could not.
That is the same tolerance the export applies to evaluation reports, for the same
reason.
"""

import logging
from pathlib import Path
from typing import Any, cast

import aiofiles
import orjson

logger = logging.getLogger(__name__)


async def read_json_sidecar(path: Path) -> dict[str, Any] | None:
    """Return a sidecar's parsed contents, or ``None`` when it cannot be read."""
    if not path.is_file():
        return None
    try:
        async with aiofiles.open(path, mode="rb") as handle:
            raw = await handle.read()
        parsed = orjson.loads(raw)
    except (OSError, orjson.JSONDecodeError):
        logger.exception("Skipping unreadable sidecar %s", path)
        return None
    if not isinstance(parsed, dict):
        logger.warning("Skipping sidecar %s: expected a JSON object at the top level", path)
        return None
    return cast(dict[str, Any], parsed)


async def read_jsonl_sidecar(path: Path) -> list[dict[str, Any]]:
    """Return a JSONL sidecar's rows, skipping any line that does not parse.

    A line at a time, because a JSONL sidecar written by a killed evaluation ends in a
    half-written row and the rows before it are still good.
    """
    if not path.is_file():
        return []
    try:
        async with aiofiles.open(path, mode="rb") as handle:
            raw = await handle.read()
    except OSError:
        logger.exception("Skipping unreadable sidecar %s", path)
        return []

    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            parsed = orjson.loads(line)
        except orjson.JSONDecodeError:
            logger.warning("Skipping unparsable line in %s", path)
            continue
        if isinstance(parsed, dict):
            rows.append(cast(dict[str, Any], parsed))
    return rows


def object_rows(value: Any) -> list[dict[str, Any]]:
    """Return the JSON objects in ``value``, dropping anything that is not one.

    Every sidecar holds its numbers in a list of objects under some key, and every
    reader has to narrow that list before touching it. Doing it here means one place
    decides what a malformed entry costs (itself, not the file) and the readers stay
    about their own fields.
    """
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in cast(list[Any], value):
        if isinstance(item, dict):
            rows.append(cast(dict[str, Any], item))
    return rows


def number_or_none(value: Any) -> float | None:
    """Return a value as a float when it is one, else ``None``.

    A sidecar field can be null where the metric had nothing to report, and null is
    not zero here any more than it is anywhere else in the analysis path.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def key_text(value: Any) -> str:
    """Render a key as the text a dimension cell holds."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return orjson.dumps(value).decode("utf-8")
