"""Discovery file for locating a running simulation's streaming endpoint.

When a simulation starts, it writes a ``stream.json`` manifest into its run
directory. The ``glossogen serve`` process reads this file to discover live
simulations and proxy their SSE streams. The manifest is deleted when the
simulation ends or crashes.
"""

import logging
import os
from pathlib import Path

import orjson
from pydantic import BaseModel

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "stream.json"


class StreamManifest(BaseModel):
    """Describes a running simulation's streaming endpoint."""

    host: str
    port: int
    run_id: str
    pid: int


def write_manifest(run_dir: Path, manifest: StreamManifest) -> None:
    """Write the stream manifest to the run directory."""
    path = run_dir / MANIFEST_FILENAME
    data = orjson.dumps(manifest.model_dump(mode="json"))
    path.write_bytes(data)
    logger.info("Wrote stream manifest: %s (port=%d)", path, manifest.port)


def read_manifest(run_dir: Path) -> StreamManifest | None:
    """Read the stream manifest from a run directory.

    Returns None if the file does not exist or if the referenced process
    is no longer alive (stale manifest).
    """
    path = run_dir / MANIFEST_FILENAME
    if not path.exists():
        return None

    raw = orjson.loads(path.read_bytes())
    manifest = StreamManifest.model_validate(raw)

    if not _is_process_alive(pid=manifest.pid):
        logger.debug("Stale stream manifest (PID %d dead): %s", manifest.pid, path)
        return None

    return manifest


def delete_manifest(run_dir: Path) -> None:
    """Remove the stream manifest from the run directory if it exists."""
    path = run_dir / MANIFEST_FILENAME
    if path.exists():
        path.unlink()
        logger.info("Deleted stream manifest: %s", path)


def _is_process_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
