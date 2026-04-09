"""FastAPI router for downloading simulation run artifacts as a zip archive."""

import asyncio
import io
import logging
import zipfile
from pathlib import Path

from dulwich.objects import Blob, Commit, Tree
from dulwich.repo import Repo
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from schmidt.run_repository import RunRepository
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


def _should_include_path(relative_path: str) -> bool:
    """Return True if a relative path string should be included in the artifact zip.

    String-based variant of ``_should_include`` for use with git tree entries
    where no filesystem Path exists.
    """
    parts = relative_path.split("/")
    for part in parts:
        if part in EXCLUDED_NAMES:
            return False
    name = parts[-1]
    for suffix in EXCLUDED_SUFFIXES:
        if name.endswith(suffix):
            return False
    return True


def _walk_tree(repo: Repo, tree: Tree, prefix: str, zf: zipfile.ZipFile) -> None:
    """Recursively walk a dulwich Tree, adding included blobs to the zip."""
    for entry in tree.items():
        name = entry.path.decode()
        if prefix:
            full_path = f"{prefix}/{name}"
        else:
            full_path = name
        obj = repo[entry.sha]
        if isinstance(obj, Tree):
            _walk_tree(repo=repo, tree=obj, prefix=full_path, zf=zf)
        elif isinstance(obj, Blob):
            if _should_include_path(relative_path=full_path):
                zf.writestr(full_path, obj.data)


def _build_zip_bytes_at_commit(run_dir: Path, commit_sha: str) -> bytes:
    """Build a zip from the git tree at a specific commit without checkout.

    Reads git objects directly via dulwich, so this is safe for concurrent
    access and does not mutate the working directory.
    """
    repo = Repo(str(run_dir))
    commit_obj = repo[commit_sha.encode()]
    if not isinstance(commit_obj, Commit):
        raise ValueError(f"SHA {commit_sha} is not a commit")
    tree_obj = repo[commit_obj.tree]
    if not isinstance(tree_obj, Tree):
        raise ValueError(f"Commit {commit_sha} does not point to a tree")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        _walk_tree(repo=repo, tree=tree_obj, prefix="", zf=zf)
    return buffer.getvalue()


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


@router.get(
    "/runs/{run_id}/export/artifacts/{message_id}",
    responses={
        200: {
            "description": "Zip archive of artifacts at a specific message commit.",
            "content": {"application/zip": {}},
        },
    },
)
async def export_run_artifacts_at_message(
    run_id: str,
    message_id: str,
    request: Request,
) -> StreamingResponse:
    """Export artifacts from a simulation run as they existed at a specific message."""
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)

    matching = [s for s in summaries if s.run_id == run_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Run not found")

    run_summary = matching[0]
    run_dir = Path(run_summary.run_dir)

    repo = RunRepository(run_dir=run_dir)
    commit_sha = await repo.find_commit_for_message(message_id=message_id)
    if commit_sha is None:
        raise HTTPException(
            status_code=404,
            detail="No snapshot found for this message",
        )

    zip_bytes = await asyncio.to_thread(
        _build_zip_bytes_at_commit,
        run_dir,
        commit_sha,
    )

    run_id_short = run_id[:8]
    message_id_short = message_id[:8]
    filename = (
        f"{run_summary.scenario_name}_{run_id_short}_{message_id_short}_artifacts.zip"
    )

    return StreamingResponse(
        content=io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
