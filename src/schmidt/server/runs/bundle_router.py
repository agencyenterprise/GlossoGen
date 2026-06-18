"""FastAPI router for exporting and importing simulation run bundles.

A bundle is a tar.gz archive of the entire run directory, enabling full
run portability between machines. A separate zip export produces a
human-extractable archive: ``{run_dir_name}.zip`` containing a single
top-level ``{run_dir_name}/`` folder, so it drops straight into a
scenario's runs directory.
"""

import asyncio
import io
import logging
import shutil
import tarfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import orjson
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from schmidt.event_parsing import parse_event_bytes
from schmidt.models.event import RunStatus, SimulationStarted
from schmidt.run_archive import claim_run_dir, strip_legacy_git_dir
from schmidt.server.runs.discovery import compose_run_id
from schmidt.server.runs.listing import list_runs_for_group
from schmidt.server.runs.lookup import register_new_run, resolve_run_or_404
from schmidt.server.runs.models import BundleManifest, ImportBundleResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")

BUNDLE_EXCLUDED_NAMES: set[str] = {
    ".git",
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
    """Return True if the file or directory should be included in the bundle tar.gz."""
    relative = path.relative_to(run_dir)
    for part in relative.parts:
        if part in BUNDLE_EXCLUDED_NAMES:
            return False
    name = relative.name
    for suffix in BUNDLE_EXCLUDED_SUFFIXES:
        if name.endswith(suffix):
            return False
    return True


def build_bundle_bytes(
    run_dir: Path,
    run_id: str,
    scenario_name: str,
    original_timestamp: int,
) -> bytes:
    """Build a tar.gz archive of the run directory."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for entry_path in sorted(run_dir.rglob("*")):
            if not _should_include_in_bundle(path=entry_path, run_dir=run_dir):
                continue
            arcname = str(entry_path.relative_to(run_dir))
            tar.add(name=str(entry_path), arcname=arcname, recursive=False)

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


def _read_origin_run_id(run_dir: Path, scenario_name: str, fallback: str) -> str:
    """Return the run's immutable identity from the JSONL's SimulationStarted event.

    The directory name can drift from this identity after a collision-rename on
    a prior import, so the bundle must record the JSONL run_id (not the dir
    name) to stay importable across machines. Falls back to ``fallback`` if the
    JSONL can't be read or its first event isn't a SimulationStarted.
    """
    jsonl_path = run_dir / f"{scenario_name}.jsonl"
    try:
        with jsonl_path.open("rb") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                event = parse_event_bytes(raw_bytes=stripped)
                if isinstance(event, SimulationStarted):
                    return event.run_id
                break
    except Exception:
        logger.exception("Failed to read origin run_id from %s", jsonl_path)
    return fallback


@router.get(
    "/runs/{scenario}/{run_dir_name}/export/bundle",
    responses={
        200: {
            "description": "Tar.gz bundle of the simulation run.",
            "content": {"application/gzip": {}},
        },
    },
)
async def export_run_bundle(
    scenario: str,
    run_dir_name: str,
    request: Request,
) -> StreamingResponse:
    """Export a simulation run as a tar.gz bundle."""
    resolved = await resolve_run_or_404(
        request=request,
        scenario=scenario,
        run_dir_name=run_dir_name,
    )

    run_id = _read_origin_run_id(
        run_dir=resolved.run_dir,
        scenario_name=resolved.scenario_name,
        fallback=compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name),
    )
    original_timestamp = int(resolved.run_dir.name.split("_")[0])

    bundle_bytes = await asyncio.to_thread(
        build_bundle_bytes,
        resolved.run_dir,
        run_id,
        resolved.scenario_name,
        original_timestamp,
    )

    filename = f"{resolved.scenario_name}_{run_dir_name}_bundle.tar.gz"

    return StreamingResponse(
        content=io.BytesIO(bundle_bytes),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


_ZIP_MIN_DATE_TIME: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)


def _zip_date_time(mtime: float) -> tuple[int, int, int, int, int, int]:
    """Return a zip-compatible ``date_time`` tuple, clamped to the 1980 epoch.

    The zip format cannot represent timestamps before 1980; run directories
    copied or extracted from older archives can carry such mtimes.
    """
    parts = time.localtime(mtime)
    if parts.tm_year < 1980:
        return _ZIP_MIN_DATE_TIME
    return (parts.tm_year, parts.tm_mon, parts.tm_mday, parts.tm_hour, parts.tm_min, parts.tm_sec)


def build_run_zip_bytes(run_dir: Path, run_dir_name: str) -> bytes:
    """Build a zip archive nesting the run files under a ``{run_dir_name}/`` folder.

    Applies the same include/exclude rules as the tar.gz bundle but omits the
    bundle manifest, so extracting the archive into a scenario's runs directory
    reproduces the original ``{run_dir_name}/`` run directory verbatim.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry_path in sorted(run_dir.rglob("*")):
            if not entry_path.is_file():
                continue
            if not _should_include_in_bundle(path=entry_path, run_dir=run_dir):
                continue
            arcname = str(Path(run_dir_name) / entry_path.relative_to(run_dir))
            info = zipfile.ZipInfo(
                filename=arcname,
                date_time=_zip_date_time(mtime=entry_path.stat().st_mtime),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            with entry_path.open("rb") as source, archive.open(info, mode="w") as target:
                shutil.copyfileobj(source, target)
    return buffer.getvalue()


@router.get(
    "/runs/{scenario}/{run_dir_name}/export/zip",
    responses={
        200: {
            "description": "Zip archive of the simulation run, nested under a run-id folder.",
            "content": {"application/zip": {}},
        },
    },
)
async def export_run_zip(
    scenario: str,
    run_dir_name: str,
    request: Request,
) -> StreamingResponse:
    """Export a simulation run as a ``{run_dir_name}.zip`` for manual extraction."""
    resolved = await resolve_run_or_404(
        request=request,
        scenario=scenario,
        run_dir_name=run_dir_name,
    )

    folder_name = resolved.run_dir.name
    zip_bytes = await asyncio.to_thread(
        build_run_zip_bytes,
        resolved.run_dir,
        folder_name,
    )

    filename = f"{folder_name}.zip"

    return StreamingResponse(
        content=io.BytesIO(zip_bytes),
        media_type="application/zip",
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


def _rename_to_original_timestamp(run_dir: Path, original_timestamp: int) -> Path:
    """Rename a run directory to use the original timestamp from the bundle.

    On collision, advances the target timestamp by one second until a free
    slot is found, mirroring ``claim_run_dir``'s "step the timestamp" approach
    so dir names stay timestamp-only (no ``_N`` suffix).
    """
    parent = run_dir.parent
    target_ts = original_timestamp
    while True:
        candidate = parent / str(target_ts)
        if run_dir.name == candidate.name:
            return run_dir
        if not candidate.exists():
            run_dir.rename(candidate)
            return candidate
        target_ts += 1


class _BundleImportOutcome(NamedTuple):
    """Result of a bundle import attempt.

    ``freshly_extracted`` is ``False`` when the run was already present on
    disk and the call short-circuited; the caller skips the ``runs`` row
    insert in that case, since a row already exists.
    """

    response: ImportBundleResponse
    freshly_extracted: bool


def _extract_and_validate_bundle(
    tar_bytes: bytes,
    runs_dir: Path,
    existing_run_dirs: dict[str, str],
) -> _BundleImportOutcome:
    """Validate and extract a bundle tar.gz into the runs directory.

    Performs all validation before extraction, and cleans up on failure.
    Import is idempotent: if a run with the same run_id already exists, returns
    the existing run without re-extracting.
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

        # The JSONL's run_id is the run's immutable identity. ``manifest.run_id``
        # can legitimately differ from it when the exporting machine's run
        # directory was renamed on a prior import (collision bumps the
        # timestamp), so a mismatch is not a corruption signal — trust the
        # JSONL and proceed.
        if jsonl_run_id != manifest.run_id:
            logger.warning(
                "Bundle manifest run_id %s differs from JSONL run_id %s "
                "(run dir likely renamed on a prior import); using the JSONL run_id",
                manifest.run_id,
                jsonl_run_id,
            )
        canonical_run_id = jsonl_run_id

        existing_dir = existing_run_dirs.get(canonical_run_id)
        if existing_dir is not None:
            logger.info(
                "Run %s already exists at %s — skipping extraction (idempotent import)",
                canonical_run_id,
                existing_dir,
            )
            return _BundleImportOutcome(
                response=ImportBundleResponse(
                    run_id=canonical_run_id,
                    scenario_name=manifest.scenario_name,
                    run_dir=existing_dir,
                ),
                freshly_extracted=False,
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
                status_code=422,
                detail="Failed to extract bundle",
            )

    # Rename directory to preserve the original timestamp so the run list
    # shows the execution time rather than the import time.
    target_dir = _rename_to_original_timestamp(
        run_dir=run_dir,
        original_timestamp=manifest.original_timestamp,
    )

    return _BundleImportOutcome(
        response=ImportBundleResponse(
            run_id=canonical_run_id,
            scenario_name=manifest.scenario_name,
            run_dir=str(target_dir),
        ),
        freshly_extracted=True,
    )


@router.post(
    "/runs/import",
    response_model=ImportBundleResponse,
    responses={
        422: {"description": "Invalid or incomplete bundle."},
    },
)
async def import_run_bundle(
    file: UploadFile,
    request: Request,
) -> ImportBundleResponse:
    """Import a simulation run from an exported bundle tar.gz.

    Idempotent: if a run with the same run_id already exists, returns the
    existing run without re-importing.
    """
    runs_dir: Path = request.app.state.runs_dir

    tar_bytes = await file.read()
    if not tar_bytes:
        raise HTTPException(status_code=422, detail="Empty file upload")

    try:
        tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz").close()
    except tarfile.TarError:
        raise HTTPException(status_code=422, detail="File is not a valid tar.gz archive")

    summaries = await list_runs_for_group(request=request, scenario_filter=None)
    existing_run_dirs = {s.run_id: s.run_dir for s in summaries}

    outcome = await asyncio.to_thread(
        _extract_and_validate_bundle,
        tar_bytes,
        runs_dir,
        existing_run_dirs,
    )

    if outcome.freshly_extracted:
        run_dir = Path(outcome.response.run_dir)
        strip_legacy_git_dir(run_dir=run_dir)
        await register_new_run(
            request=request,
            scenario=outcome.response.scenario_name,
            run_dir_name=run_dir.name,
            status=RunStatus.SCENARIO_COMPLETE.value,
            source_run_scenario=None,
            source_run_dir_name=None,
        )
        logger.info(
            "Imported run %s (%s) to %s",
            outcome.response.run_id,
            outcome.response.scenario_name,
            outcome.response.run_dir,
        )

    return outcome.response
