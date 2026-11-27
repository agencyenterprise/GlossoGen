"""FastAPI router for exporting and importing simulation run bundles.

A bundle is a tar.gz archive of the entire run directory, enabling full
run portability between machines. A separate zip export produces a
human-extractable archive: ``{run_dir_name}.zip`` containing a single
top-level ``{run_dir_name}/`` folder, so it drops straight into a
scenario's runs directory. The Inspect export writes the run's agents as one
Inspect-format log for Docent.
"""

import asyncio
import io
import logging
import shutil
import tarfile
from pathlib import Path
from typing import IO, NamedTuple

import orjson
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from glossogen.atif_export.inspect_log_builder import (
    INSPECT_LOG_FILE_NAME,
    InspectLog,
    build_inspect_samples,
    serialize_inspect_log,
)
from glossogen.models.event import RunStatus, SimulationStarted
from glossogen.run_export.export_limits import ExportTooLargeError, check_raw_bytes
from glossogen.run_export.run_trajectory_loader import load_run_trajectories
from glossogen.run_export.runs_zip_archive import write_single_run_zip
from glossogen.run_storage.archive_member_filter import is_always_excluded
from glossogen.run_storage.event_parsing import parse_event_bytes
from glossogen.run_storage.history_transfer_manifest import read_history_transfer_manifest
from glossogen.run_storage.jsonl_lines import first_nonblank_line
from glossogen.run_storage.run_archive import claim_run_dir
from glossogen.run_storage.run_bundle import (
    BUNDLE_MANIFEST_FILENAME,
    BundleManifest,
    build_bundle_bytes,
)
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.run_storage.run_identity import compose_run_id
from glossogen.run_storage.run_labels_file import read_run_labels
from glossogen.run_storage.run_lineage import TimelineParent, read_timeline_parent
from glossogen.run_storage.run_summary_models import RunSummary
from glossogen.scenario_contract.scenario_name import is_valid_scenario_name
from glossogen.server.runs.archive_streaming_response import (
    build_temp_file_archive_response,
)
from glossogen.server.runs.bundle_tar_limits import (
    MAX_BUNDLE_MEMBER_COUNT,
    BundleHeaderTooLargeError,
    BundleTarFile,
)
from glossogen.server.runs.listing import list_runs_for_group
from glossogen.server.runs.lookup import register_new_run, resolve_run_or_404
from glossogen.server.runs.models import ImportBundleResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")


def _read_origin_run_id(run_dir: Path, scenario_name: str, fallback: str) -> str:
    """Return the run's immutable identity from the JSONL's SimulationStarted event.

    The directory name can drift from this identity after a collision-rename on
    a prior import, so the bundle must record the JSONL run_id (not the dir
    name) to stay importable across machines. Falls back to ``fallback`` if the
    JSONL can't be read or its first event isn't a SimulationStarted.
    """
    jsonl_path = event_log_path(run_dir=run_dir, scenario_name=scenario_name)
    try:
        with jsonl_path.open("rb") as handle:
            first_line = first_nonblank_line(lines=handle)
        if first_line is not None:
            event = parse_event_bytes(raw_bytes=first_line, scenario_name=scenario_name)
            if isinstance(event, SimulationStarted):
                return event.run_id
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
    """Export a simulation run as a ``{run_dir_name}.zip`` for manual extraction.

    Each agent's ATIF trajectory is included under ``atif/``.
    """
    resolved = await resolve_run_or_404(
        request=request,
        scenario=scenario,
        run_dir_name=run_dir_name,
    )

    folder_name = resolved.run_dir.name

    def build(destination: IO[bytes]) -> None:
        write_single_run_zip(
            run_dir=resolved.run_dir,
            run_dir_name=folder_name,
            scenario_name=resolved.scenario_name,
            include_logs=False,
            include_atif=True,
            destination=destination,
        )

    return await build_temp_file_archive_response(
        build=build,
        filename=f"{folder_name}.zip",
        media_type="application/zip",
    )


def _build_run_inspect_log(run_dir: Path, scenario_name: str) -> bytes | None:
    """The run's Inspect log, or None when the run has no trajectories to put in it."""
    trajectories = load_run_trajectories(run_dir=run_dir, scenario_name=scenario_name)
    if not trajectories:
        return None
    log = InspectLog(samples=build_inspect_samples(trajectories=trajectories))
    return serialize_inspect_log(log=log).encode("utf-8")


@router.get(
    "/runs/{scenario}/{run_dir_name}/export/inspect",
    responses={
        200: {
            "description": "The run's agents as one Inspect-format log, for Docent.",
            "content": {"application/json": {}},
        },
    },
)
async def export_run_inspect_log(
    scenario: str,
    run_dir_name: str,
    request: Request,
) -> Response:
    """Export every agent of a run as one Inspect-format log file."""
    resolved = await resolve_run_or_404(
        request=request,
        scenario=scenario,
        run_dir_name=run_dir_name,
    )
    payload = await asyncio.to_thread(
        _build_run_inspect_log,
        resolved.run_dir,
        resolved.scenario_name,
    )
    if payload is None:
        raise HTTPException(
            status_code=422,
            detail="This run has no agent trajectories: its event log is missing or unreadable.",
        )
    filename = f"{resolved.scenario_name}_{resolved.run_dir.name}_{INSPECT_LOG_FILE_NAME}"
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _validate_tar_members(tar: tarfile.TarFile) -> None:
    """Reject unsafe paths, archives over the raw-export size ceiling, and archives
    with more than :data:`MAX_BUNDLE_MEMBER_COUNT` members.

    Members are read one at a time, so an archive over the member ceiling is refused
    without reading the rest of it. Every member's size counts toward the ceiling,
    not only a regular file's: ``tarfile`` decompresses and skips the data of a
    member whose type it does not know.
    """
    total_bytes = 0
    for member_count, member in enumerate(tar, start=1):
        if member_count > MAX_BUNDLE_MEMBER_COUNT:
            raise ExportTooLargeError(
                f"This bundle has more than {MAX_BUNDLE_MEMBER_COUNT} files. "
                "A run bundle carries far fewer."
            )
        member_path = Path(member.name)
        if member_path.is_absolute():
            raise ValueError(f"Unsafe tar member path (absolute): {member.name}")
        if ".." in member_path.parts:
            raise ValueError(f"Unsafe tar member path (traversal): {member.name}")
        total_bytes += member.size
        check_raw_bytes(total_bytes=total_bytes)


def _reject_link_members(tar: tarfile.TarFile) -> None:
    """Reject any member that is not a regular file or a directory.

    An export writes only those. A link member would let a later member be written
    through it into a file whose name :func:`_run_owned_members` never sees, such as
    ``stream.json``.
    """
    for member in tar.getmembers():
        if not member.isreg() and not member.isdir():
            raise ValueError(
                f"Unsupported tar member type (not a file or directory): {member.name}"
            )


def _run_owned_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    """Return the members to extract: all but the live-state files no archive carries.

    An export leaves them out, so a bundle that holds one is stale or hand-built. The
    server trusts ``stream.json`` for the PID it signals on stop and delete and for
    the address it proxies the event stream from, so extracting it would let an
    uploader choose both.
    """
    return [
        member
        for member in tar.getmembers()
        if not is_always_excluded(relative_path=Path(member.name))
    ]


def _extract_manifest(tar: tarfile.TarFile) -> BundleManifest:
    """Extract and parse the bundle manifest from the tar archive."""
    member = tar.getmember(BUNDLE_MANIFEST_FILENAME)
    extracted = tar.extractfile(member)
    if extracted is None:
        raise ValueError("bundle_manifest.json is not a regular file")
    raw = orjson.loads(extracted.read())
    return BundleManifest(**raw)


def _validate_jsonl_first_event(tar: tarfile.TarFile, scenario_name: str) -> SimulationStarted:
    """Return the JSONL's first event after validating its type and scenario."""
    if not is_valid_scenario_name(name=scenario_name):
        raise ValueError(f"Invalid scenario name in bundle manifest: {scenario_name!r}")
    jsonl_name = f"{scenario_name}.jsonl"
    member = tar.getmember(jsonl_name)
    extracted = tar.extractfile(member)
    if extracted is None:
        raise ValueError(f"{jsonl_name} is not a regular file")
    first_line = first_nonblank_line(lines=extracted)
    if first_line is None:
        raise ValueError(f"{jsonl_name} is empty")
    event = parse_event_bytes(raw_bytes=first_line, scenario_name=scenario_name)
    if not isinstance(event, SimulationStarted):
        raise ValueError(f"First event in {jsonl_name} is not SimulationStarted")
    if event.scenario_name != scenario_name:
        raise ValueError(
            f"Bundle manifest names scenario {scenario_name!r}, but {jsonl_name} "
            f"records {event.scenario_name!r}"
        )
    return event


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
    insert in that case, since a row already exists. ``timeline_parent`` is
    the extracted run's, read from its manifests, and ``None`` when it was not
    extracted or is not derived.
    """

    response: ImportBundleResponse
    freshly_extracted: bool
    timeline_parent: TimelineParent | None


def _read_derivation_manifests(run_dir: Path) -> TimelineParent | None:
    """Parse every derivation manifest that names a file to read, returning the lineage.

    Those manifests name files that resume, the trajectory exports and the probes
    later read from the run directory, and the model refuses a name that leaves it.
    Parsing them here refuses such a bundle at upload instead of at first read.
    """
    read_history_transfer_manifest(run_dir=run_dir)
    return read_timeline_parent(run_dir=run_dir)


def _index_existing_run_dirs(summaries: list[RunSummary]) -> dict[str, str]:
    """Index stored runs by immutable JSONL identity."""
    return {
        _read_origin_run_id(
            run_dir=Path(summary.run_dir),
            scenario_name=summary.scenario_name,
            fallback=summary.run_id,
        ): summary.run_dir
        for summary in summaries
    }


def _extract_and_validate_bundle(
    tar_source: IO[bytes],
    runs_dir: Path,
    existing_run_dirs: dict[str, str],
) -> _BundleImportOutcome:
    """Validate and extract a bundle tar.gz stream into the runs directory.

    Performs all validation before extraction, and cleans up on failure.
    Import is idempotent: if a run with the same run_id already exists, returns
    the existing run without re-extracting.
    """
    with BundleTarFile.open(fileobj=tar_source, mode="r:gz") as tar:
        _validate_tar_members(tar=tar)
        _reject_link_members(tar=tar)

        try:
            manifest = _extract_manifest(tar=tar)
        except KeyError:
            logger.exception("Bundle is missing %s", BUNDLE_MANIFEST_FILENAME)
            raise HTTPException(
                status_code=422,
                detail="Bundle is missing bundle_manifest.json",
            )

        try:
            first_event = _validate_jsonl_first_event(
                tar=tar,
                scenario_name=manifest.scenario_name,
            )
        except KeyError:
            logger.exception("Bundle is missing %s.jsonl", manifest.scenario_name)
            raise HTTPException(
                status_code=422,
                detail=f"Bundle is missing {manifest.scenario_name}.jsonl",
            )

        # The JSONL's run_id is the run's immutable identity. ``manifest.run_id``
        # can legitimately differ from it when the exporting machine's run
        # directory was renamed on a prior import (collision bumps the
        # timestamp), so a mismatch is not a corruption signal — trust the
        # JSONL and proceed.
        if first_event.run_id != manifest.run_id:
            logger.warning(
                "Bundle manifest run_id %s differs from JSONL run_id %s "
                "(run dir likely renamed on a prior import); using the JSONL run_id",
                manifest.run_id,
                first_event.run_id,
            )
        canonical_run_id = first_event.run_id

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
                timeline_parent=None,
            )

        run_dir = claim_run_dir(
            runs_dir=runs_dir,
            scenario_name=manifest.scenario_name,
        )

        try:
            tar.extractall(
                path=str(run_dir),
                members=_run_owned_members(tar=tar),
                filter="data",
            )
        except Exception:
            logger.exception("Failed to extract bundle to %s", run_dir)
            shutil.rmtree(run_dir, ignore_errors=True)
            raise HTTPException(
                status_code=422,
                detail="Failed to extract bundle",
            )

        try:
            timeline_parent = _read_derivation_manifests(run_dir=run_dir)
        except ValueError as exc:
            # A ValidationError, or a lineage run id with no scenario part.
            logger.exception("Bundle extracted to %s carries an invalid manifest", run_dir)
            shutil.rmtree(run_dir, ignore_errors=True)
            raise HTTPException(
                status_code=422,
                detail=f"Invalid bundle: a derivation manifest does not parse: {exc}",
            ) from exc

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
        timeline_parent=timeline_parent,
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

    await file.seek(0)
    if not await file.read(1):
        raise HTTPException(status_code=422, detail="Empty file upload")
    await file.seek(0)

    if file.size is not None:
        try:
            check_raw_bytes(total_bytes=file.size)
        except ExportTooLargeError as exc:
            logger.exception("Bundle upload exceeds the raw export size limit")
            raise HTTPException(status_code=413, detail=str(exc)) from exc

    summaries = await list_runs_for_group(request=request, scenario_filter=None)
    existing_run_dirs = await asyncio.to_thread(_index_existing_run_dirs, summaries)

    try:
        outcome = await asyncio.to_thread(
            _extract_and_validate_bundle,
            file.file,
            runs_dir,
            existing_run_dirs,
        )
    except HTTPException:
        logger.exception("Bundle import rejected")
        raise
    except (ExportTooLargeError, BundleHeaderTooLargeError) as exc:
        logger.exception("Bundle import exceeds a bundle size limit")
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except (ValueError, tarfile.TarError) as exc:
        logger.exception("Bundle import is invalid")
        raise HTTPException(status_code=422, detail=f"Invalid bundle: {exc}") from exc

    if outcome.freshly_extracted:
        run_dir = Path(outcome.response.run_dir)
        timeline_parent = outcome.timeline_parent
        source_run_scenario: str | None = None
        source_run_dir_name: str | None = None
        if timeline_parent is not None:
            source_run_scenario = timeline_parent.scenario
            source_run_dir_name = timeline_parent.run_dir_name
        # Bundles carry labels.json, so the imported run's mirror is seeded
        # from the file just extracted rather than left for the backfill.
        await register_new_run(
            request=request,
            scenario=outcome.response.scenario_name,
            run_dir_name=run_dir.name,
            status=RunStatus.SCENARIO_COMPLETE.value,
            source_run_scenario=source_run_scenario,
            source_run_dir_name=source_run_dir_name,
            labels=read_run_labels(run_dir=run_dir),
        )
        logger.info(
            "Imported run %s (%s) to %s",
            outcome.response.run_id,
            outcome.response.scenario_name,
            outcome.response.run_dir,
        )

    return outcome.response
