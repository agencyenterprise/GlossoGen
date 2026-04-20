"""FastAPI router for exporting and importing simulation run bundles.

A bundle is a tar.gz archive of the entire run directory including git history,
enabling full run portability between machines with fork support preserved.
"""

import asyncio
import io
import logging
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import orjson
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from schmidt.event_parsing import parse_event_bytes
from schmidt.models.event import SimulationStarted
from schmidt.run_repository import RunRepository, claim_run_dir
from schmidt.server.runs.discovery import discover_runs, resolve_run
from schmidt.server.runs.models import BundleManifest, ImportBundleResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

BUNDLE_EXCLUDED_NAMES: set[str] = {
    "stream.json",
    "eval_in_progress.json",
    "eval_stdout.log",
}

BUNDLE_EXCLUDED_SUFFIXES: tuple[str, ...] = (
    "_debug.jsonl",
    "_stdout.log",
    "_start.log",
)

_MANIFEST_FILENAME = "bundle_manifest.json"


def _should_include_in_bundle(path: Path, run_dir: Path) -> bool:
    """Return True if the file should be included in the bundle tar.gz."""
    relative = path.relative_to(run_dir)
    name = relative.name
    if name in BUNDLE_EXCLUDED_NAMES:
        return False
    for suffix in BUNDLE_EXCLUDED_SUFFIXES:
        if name.endswith(suffix):
            return False
    return True


def _pack_git_objects(run_dir: Path) -> None:
    """Run git gc to pack loose objects, dramatically reducing .git size.

    Loose objects store each JSONL snapshot as a separate blob. Packing
    enables delta compression across commits, typically shrinking .git
    from hundreds of megabytes to a few megabytes.
    """
    git_dir = run_dir / ".git"
    if not git_dir.is_dir():
        return
    subprocess.run(
        ["git", "gc", "--aggressive", "--quiet"],
        cwd=str(run_dir),
        check=True,
        capture_output=True,
        timeout=360,
    )


def _build_bundle_bytes(
    run_dir: Path,
    run_id: str,
    scenario_name: str,
    original_timestamp: int,
) -> bytes:
    """Build a tar.gz archive of the run directory including git history."""
    _pack_git_objects(run_dir=run_dir)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for file_path in sorted(run_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if not _should_include_in_bundle(path=file_path, run_dir=run_dir):
                continue
            arcname = str(file_path.relative_to(run_dir))
            tar.add(name=str(file_path), arcname=arcname)

        manifest = BundleManifest(
            run_id=run_id,
            scenario_name=scenario_name,
            exported_at=datetime.now(tz=UTC),
            original_timestamp=original_timestamp,
        )
        manifest_bytes = orjson.dumps(manifest.model_dump(mode="json"), option=orjson.OPT_INDENT_2)
        info = tarfile.TarInfo(name=_MANIFEST_FILENAME)
        info.size = len(manifest_bytes)
        tar.addfile(tarinfo=info, fileobj=io.BytesIO(manifest_bytes))

    return buffer.getvalue()


@router.get(
    "/runs/{run_id}/export/bundle",
    responses={
        200: {
            "description": "Tar.gz bundle of the simulation run with git history.",
            "content": {"application/gzip": {}},
        },
    },
)
async def export_run_bundle(run_id: str, request: Request) -> StreamingResponse:
    """Export a simulation run as a tar.gz bundle including git history."""
    runs_dir: Path = request.app.state.runs_dir
    try:
        resolved = await resolve_run(runs_dir=runs_dir, run_id=run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")

    original_timestamp = int(resolved.run_dir.name.split("_")[0])

    bundle_bytes = await asyncio.to_thread(
        _build_bundle_bytes,
        resolved.run_dir,
        run_id,
        resolved.scenario_name,
        original_timestamp,
    )

    run_id_short = run_id[:8]
    filename = f"{resolved.scenario_name}_{run_id_short}_bundle.tar.gz"

    return StreamingResponse(
        content=io.BytesIO(bundle_bytes),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


def _validate_tar_members(tar: tarfile.TarFile) -> None:
    """Reject tar members with path traversal or absolute paths."""
    for member in tar.getmembers():
        member_path = Path(member.name)
        if member_path.is_absolute():
            raise ValueError(f"Unsafe tar member path (absolute): {member.name}")
        if ".." in member_path.parts:
            raise ValueError(f"Unsafe tar member path (traversal): {member.name}")


def _extract_manifest(tar: tarfile.TarFile) -> BundleManifest:
    """Extract and parse the bundle manifest from the tar archive."""
    member = tar.getmember(_MANIFEST_FILENAME)
    extracted = tar.extractfile(member)
    if extracted is None:
        raise ValueError("bundle_manifest.json is not a regular file")
    raw = orjson.loads(extracted.read())
    return BundleManifest(**raw)


def _validate_jsonl_first_event(tar: tarfile.TarFile, scenario_name: str) -> str:
    """Validate that the JSONL contains a SimulationStarted event. Returns the run_id."""
    jsonl_name = f"{scenario_name}.jsonl"
    member = tar.getmember(jsonl_name)
    extracted = tar.extractfile(member)
    if extracted is None:
        raise ValueError(f"{jsonl_name} is not a regular file")
    first_line = b""
    for line in extracted:
        stripped = line.strip()
        if stripped:
            first_line = stripped
            break
    if not first_line:
        raise ValueError(f"{jsonl_name} is empty")
    event = parse_event_bytes(raw_bytes=first_line)
    if not isinstance(event, SimulationStarted):
        raise ValueError(f"First event in {jsonl_name} is not SimulationStarted")
    return event.run_id


def _has_git_members(tar: tarfile.TarFile) -> bool:
    """Check whether the tar contains .git/ directory entries."""
    for member in tar.getmembers():
        if member.name.startswith(".git/"):
            return True
    return False


def _rename_to_original_timestamp(run_dir: Path, original_timestamp: int) -> Path:
    """Rename a run directory to use the original timestamp from the bundle.

    Uses the same collision-avoidance suffix scheme as claim_run_dir. If the
    directory already has the correct name, returns it unchanged.
    """
    target_name = str(original_timestamp)
    if run_dir.name == target_name:
        return run_dir

    parent = run_dir.parent
    candidate = parent / target_name
    if not candidate.exists():
        run_dir.rename(candidate)
        return candidate

    # Collision: append _2, _3, ... until we find a free slot.
    suffix = 2
    while True:
        candidate = parent / f"{target_name}_{suffix}"
        if not candidate.exists():
            run_dir.rename(candidate)
            return candidate
        suffix += 1


def _extract_and_validate_bundle(
    tar_bytes: bytes,
    runs_dir: Path,
    existing_run_ids: set[str],
) -> ImportBundleResponse:
    """Validate and extract a bundle tar.gz into the runs directory.

    Performs all validation before extraction, and cleans up on failure.
    """
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        _validate_tar_members(tar=tar)

        try:
            manifest = _extract_manifest(tar=tar)
        except KeyError:
            raise HTTPException(
                status_code=422,
                detail="Bundle is missing bundle_manifest.json",
            )

        try:
            jsonl_run_id = _validate_jsonl_first_event(
                tar=tar,
                scenario_name=manifest.scenario_name,
            )
        except KeyError:
            raise HTTPException(
                status_code=422,
                detail=f"Bundle is missing {manifest.scenario_name}.jsonl",
            )

        if jsonl_run_id != manifest.run_id:
            raise HTTPException(
                status_code=422,
                detail="run_id in JSONL does not match bundle manifest",
            )

        if not _has_git_members(tar=tar):
            raise HTTPException(
                status_code=422,
                detail="Bundle is missing git history (.git/ directory)",
            )

        if manifest.run_id in existing_run_ids:
            raise HTTPException(
                status_code=409,
                detail=f"Run {manifest.run_id} already exists",
            )

        run_dir = claim_run_dir(
            runs_dir=runs_dir,
            scenario_name=manifest.scenario_name,
        )

        try:
            tar.extractall(path=str(run_dir), filter="data")
        except Exception:
            logger.exception("Failed to extract bundle to %s", run_dir)
            shutil.rmtree(run_dir, ignore_errors=True)
            raise HTTPException(
                status_code=500,
                detail="Failed to extract bundle",
            )

    # Rename directory to preserve the original timestamp so the run list
    # shows the execution time rather than the import time.
    target_dir = _rename_to_original_timestamp(
        run_dir=run_dir,
        original_timestamp=manifest.original_timestamp,
    )

    return ImportBundleResponse(
        run_id=manifest.run_id,
        scenario_name=manifest.scenario_name,
        run_dir=str(target_dir),
    )


@router.post(
    "/runs/import",
    response_model=ImportBundleResponse,
    responses={
        409: {"description": "Run with this ID already exists."},
        422: {"description": "Invalid or incomplete bundle."},
    },
)
async def import_run_bundle(
    file: UploadFile,
    request: Request,
) -> ImportBundleResponse:
    """Import a simulation run from an exported bundle tar.gz."""
    runs_dir: Path = request.app.state.runs_dir

    tar_bytes = await file.read()
    if not tar_bytes:
        raise HTTPException(status_code=422, detail="Empty file upload")

    try:
        tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz").close()
    except tarfile.TarError:
        raise HTTPException(status_code=422, detail="File is not a valid tar.gz archive")

    summaries = await discover_runs(runs_dir=runs_dir)
    existing_run_ids = {s.run_id for s in summaries}

    result = await asyncio.to_thread(
        _extract_and_validate_bundle,
        tar_bytes,
        runs_dir,
        existing_run_ids,
    )

    run_dir = Path(result.run_dir)
    repo = RunRepository(run_dir=run_dir)
    try:
        await repo.get_head_sha()
    except Exception:
        logger.exception("Git integrity check failed for imported run at %s", run_dir)
        shutil.rmtree(run_dir, ignore_errors=True)
        raise HTTPException(
            status_code=422,
            detail="Bundle contains invalid git repository",
        )

    logger.info(
        "Imported run %s (%s) to %s",
        result.run_id,
        result.scenario_name,
        result.run_dir,
    )

    return result
