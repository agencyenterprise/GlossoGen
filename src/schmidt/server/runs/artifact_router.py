"""FastAPI router for downloading simulation run artifacts as a zip archive."""

import io
import logging
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from schmidt.server.runs.discovery import discover_runs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

EXCLUDED_NAMES = {
    ".git",
    "stream.json",
}

EXCLUDED_SUFFIXES = {
    "_debug.jsonl",
    "_stdout.log",
    "_start.log",
}


def _should_include(path: Path, run_dir: Path) -> bool:
    """Return True if the file should be included in the artifact zip."""
    relative = path.relative_to(run_dir)
    for part in relative.parts:
        if part in EXCLUDED_NAMES:
            return False
    name = path.name
    for suffix in EXCLUDED_SUFFIXES:
        if name.endswith(suffix):
            return False
    return True


def _build_zip_bytes(run_dir: Path) -> bytes:
    """Build a zip archive of the run directory in memory.

    Excludes git history, debug logs, stdout logs, and streaming manifests.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(run_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if not _should_include(path=file_path, run_dir=run_dir):
                continue
            arcname = str(file_path.relative_to(run_dir))
            zf.write(filename=file_path, arcname=arcname)
    return buffer.getvalue()


@router.get(
    "/runs/{run_id}/export/artifacts",
    responses={
        200: {
            "description": "Zip archive of the simulation run artifacts.",
            "content": {"application/zip": {}},
        },
    },
)
async def export_run_artifacts(run_id: str, request: Request) -> StreamingResponse:
    """Export all artifacts from a simulation run as a zip archive."""
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)

    matching = [s for s in summaries if s.run_id == run_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Run not found")

    run_summary = matching[0]
    run_dir = Path(run_summary.run_dir)

    zip_bytes = _build_zip_bytes(run_dir=run_dir)

    run_id_short = run_id[:8]
    filename = f"{run_summary.scenario_name}_{run_id_short}_artifacts.zip"

    return StreamingResponse(
        content=io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
