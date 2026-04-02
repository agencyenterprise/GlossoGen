"""Discovery file for detecting an in-progress evaluation subprocess.

When an evaluation starts (via CLI or web UI), it writes an ``eval_in_progress.json``
manifest into the run directory. The web server checks this file to report evaluation
status. The manifest is deleted when the evaluation finishes or crashes.
"""

import logging
import os
from pathlib import Path

import orjson
from pydantic import BaseModel

logger = logging.getLogger(__name__)

EVAL_MANIFEST_FILENAME = "eval_in_progress.json"


class EvalManifest(BaseModel):
    """Describes a running evaluation subprocess."""

    pid: int


def write_eval_manifest(run_dir: Path, pid: int) -> None:
    """Write the evaluation manifest to the run directory."""
    path = run_dir / EVAL_MANIFEST_FILENAME
    manifest = EvalManifest(pid=pid)
    data = orjson.dumps(manifest.model_dump(mode="json"))
    path.write_bytes(data)
    logger.info("Wrote eval manifest: %s (pid=%d)", path, pid)


def read_eval_manifest(run_dir: Path) -> EvalManifest | None:
    """Read the evaluation manifest from a run directory.

    Returns None if the file does not exist or if the referenced process
    is no longer alive (stale manifest).
    """
    path = run_dir / EVAL_MANIFEST_FILENAME
    if not path.exists():
        return None

    raw = orjson.loads(path.read_bytes())
    manifest = EvalManifest.model_validate(raw)

    if not _is_process_alive(pid=manifest.pid):
        logger.debug("Stale eval manifest (PID %d dead): %s", manifest.pid, path)
        return None

    return manifest


def delete_eval_manifest(run_dir: Path) -> None:
    """Remove the evaluation manifest from the run directory if it exists."""
    path = run_dir / EVAL_MANIFEST_FILENAME
    if path.exists():
        path.unlink()
        logger.info("Deleted eval manifest: %s", path)


def _is_process_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
