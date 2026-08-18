"""FastAPI router for exporting many runs at once.

Three POSTs, not GETs. The body carries a run-id list that can run to hundreds of
ids and a column list that can run to a hundred keys; as a query string that exceeds
what some browsers and reverse proxies accept, and the failure comes back as an
opaque 414 that no interface can explain. Sharing one body model between the preview
and the downloads is also what keeps "the preview describes what the download
produces" true by construction.

A slow export is answered synchronously, held down by the run-count ceiling and by
a byte ceiling per shape: run folders get sized before the build, CSV tables get
counted during it. Once a selection can outlive a proxy timeout the answer becomes a
job that is polled for, and that needs a job store, a worker, and artifact
retention. None of those exist yet, and the ceilings keep the synchronous path
honest until they do.

An oversized selection still gets a preview, so a caller can show the count beside
the ceiling. Only the downloads refuse.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import IO

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from glossogen.run_export import export_limits
from glossogen.run_export.csv_export_archive import (
    build_export_frames,
    build_legend_frame,
    write_frames_to_zip,
    write_single_frame,
)
from glossogen.run_export.export_column_catalog import (
    build_export_preview,
    estimate_raw_bytes,
    oversized_export_preview,
)
from glossogen.run_export.export_limits import (
    ExportTooLargeError,
    check_csv_bytes,
    check_raw_bytes,
    check_run_count,
)
from glossogen.run_export.export_preview_models import MultiRunExportPreview
from glossogen.run_export.export_request_models import (
    CsvExportRequest,
    ExportPreviewRequest,
    RawExportRequest,
    RunSelection,
)
from glossogen.run_export.export_run_record import ExportRunRecord, load_export_run_records
from glossogen.run_export.runs_zip_archive import write_runs_zip
from glossogen.server.runs.archive_streaming_response import build_temp_file_archive_response
from glossogen.server.runs.export_selection import resolve_export_selection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")


def _stamp() -> str:
    """Return a UTC stamp for an export filename."""
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def _delivered_bytes_check(destination: IO[bytes]) -> Callable[[], None]:
    """Return a check on how many bytes the client would receive so far.

    The destination's position is the delivered size: compressed for a zip, raw for a
    bare CSV. Counting the rows' own bytes instead would hold the two shapes of this
    endpoint to ceilings differing by the compression ratio, and CSV deflates by two
    orders of magnitude.
    """

    def check() -> None:
        """Check the bytes written so far against the ceiling."""
        check_csv_bytes(total_bytes=destination.tell())

    return check


async def _archive_or_too_large(
    build: Callable[[IO[bytes]], None],
    filename: str,
    media_type: str,
) -> StreamingResponse:
    """Build and stream an archive, mapping a breached ceiling to a status code.

    Nothing has been sent when ``build`` raises, so a ceiling hit partway through
    becomes a 413 and never a truncated download.
    """
    try:
        return await build_temp_file_archive_response(
            build=build, filename=filename, media_type=media_type
        )
    except ExportTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc


async def _resolved_records(
    request: Request,
    selection: RunSelection,
) -> list[ExportRunRecord]:
    """Resolve a selection to records, refusing an empty or oversized one.

    Missing ids are fatal for a download. A caller who asked for a run and got a
    table without it has no way to notice.
    """
    resolved = await resolve_export_selection(request=request, selection=selection)
    if resolved.missing_run_ids:
        raise HTTPException(
            status_code=404,
            detail=(
                "These runs are no longer available: "
                f"{', '.join(sorted(resolved.missing_run_ids))}"
            ),
        )
    if not resolved.summaries:
        raise HTTPException(status_code=422, detail="This selection matches no runs.")
    try:
        check_run_count(run_count=len(resolved.summaries))
    except ExportTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return await load_export_run_records(runs=resolved.summaries)


@router.post("/runs/export/preview", response_model=MultiRunExportPreview)
async def preview_multi_run_export(
    body: ExportPreviewRequest,
    request: Request,
) -> MultiRunExportPreview:
    """Describe what a selection would export, without building anything."""
    resolved = await resolve_export_selection(request=request, selection=body.selection)

    # An oversized selection is answered, not refused, so a caller can render
    # the count against the ceiling instead of guessing from an error. What it skips
    # is reading a report for every run: the offered columns come from those reports,
    # and an export that cannot run has none to offer.
    if len(resolved.summaries) > export_limits.MAX_EXPORT_RUN_COUNT:
        return oversized_export_preview(
            run_ids=[summary.run_id for summary in resolved.summaries],
            scenario_names=sorted({summary.scenario_name for summary in resolved.summaries}),
            missing_run_ids=resolved.missing_run_ids,
        )

    records = await load_export_run_records(runs=resolved.summaries)

    raw_bytes_estimate = None
    if body.include_raw_size_estimate:
        raw_bytes_estimate = estimate_raw_bytes(records=records, include_logs=body.include_logs)

    return build_export_preview(
        records=records,
        missing_run_ids=resolved.missing_run_ids,
        raw_bytes_estimate=raw_bytes_estimate,
    )


@router.post(
    "/runs/export/raw",
    responses={
        200: {
            "description": "Zip of the selected run folders, nested per scenario and run.",
            "content": {"application/zip": {}},
        },
    },
)
async def export_runs_raw(
    body: RawExportRequest,
    request: Request,
) -> StreamingResponse:
    """Export the selected runs' folders as one zip."""
    records = await _resolved_records(request=request, selection=body.selection)
    summaries = [record.summary for record in records]

    # Sizing the selection first means an oversized one is refused before any
    # compression happens, and while a status code can still be returned.
    estimated_bytes = estimate_raw_bytes(records=records, include_logs=body.include_logs)
    try:
        check_raw_bytes(total_bytes=estimated_bytes)
    except ExportTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    logger.info("Raw export of %d runs, about %d bytes", len(summaries), estimated_bytes)

    def build(destination: IO[bytes]) -> None:
        write_runs_zip(
            runs=summaries,
            include_logs=body.include_logs,
            destination=destination,
        )

    return await build_temp_file_archive_response(
        build=build,
        filename=f"glossogen_runs_{_stamp()}.zip",
        media_type="application/zip",
    )


@router.post(
    "/runs/export/csv",
    # The endpoint answers with either a bare CSV or a zip, so the shape is
    # declared in ``responses`` and there is no model to infer from the return type.
    response_model=None,
    responses={
        200: {
            "description": "One CSV when a single table was asked for, otherwise a zip of them.",
            "content": {"text/csv": {}, "application/zip": {}},
        },
    },
)
async def export_runs_csv(
    body: CsvExportRequest,
    request: Request,
) -> StreamingResponse:
    """Export the selected runs as CSV tables."""
    if not body.frames:
        raise HTTPException(status_code=422, detail="Choose at least one table to export.")
    if not body.columns and not body.metrics:
        raise HTTPException(status_code=422, detail="Choose at least one column to export.")

    records = await _resolved_records(request=request, selection=body.selection)
    frames = build_export_frames(records=records, request=body)

    if len(frames) == 1:
        single = frames[0]

        def build_csv(destination: IO[bytes]) -> None:
            write_single_frame(
                frame=single,
                destination=destination,
                check=_delivered_bytes_check(destination=destination),
            )

        return await _archive_or_too_large(
            build=build_csv,
            filename=f"{single.name}_{_stamp()}.csv",
            media_type="text/csv",
        )

    legend = build_legend_frame(records=records, request=body)

    def build(destination: IO[bytes]) -> None:
        write_frames_to_zip(
            frames=frames,
            legend=legend,
            destination=destination,
            check=_delivered_bytes_check(destination=destination),
        )

    return await _archive_or_too_large(
        build=build,
        filename=f"glossogen_csv_{_stamp()}.zip",
        media_type="application/zip",
    )
