"""FastAPI router for metadata-only writes (labels, note, evaluation report).

Used as the ingest target for the cross-server "sync metadata to prod"
flow. Each field of the request body is optional: ``None`` leaves the
existing on-disk value untouched, while a non-null value overwrites it.
Mirrors the replace-only semantics of the existing ``PUT /labels`` and
``PUT /note`` endpoints. None of these writes are committed to git, also
matching the existing per-field endpoints.
"""

import logging
from pathlib import Path

import orjson
from fastapi import APIRouter, HTTPException, Request

from schmidt.evaluation.reports.evaluation_report import write_report
from schmidt.server.runs.discovery import compose_run_id, resolve_run
from schmidt.server.runs.models import SyncMetadataRequest, SyncMetadataResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.put(
    "/runs/{scenario}/{run_dir_name}/metadata",
    response_model=SyncMetadataResponse,
)
async def sync_run_metadata(
    scenario: str,
    run_dir_name: str,
    body: SyncMetadataRequest,
    request: Request,
) -> SyncMetadataResponse:
    """Overwrite labels / note / evaluation report for an existing run.

    Returns 404 when the run does not exist on this server. Each field of
    the body is independent: ``null`` skips the field, a value replaces it.
    """
    runs_dir: Path = request.app.state.runs_dir
    try:
        resolved = resolve_run(
            runs_dir=runs_dir,
            scenario_name=scenario,
            run_dir_name=run_dir_name,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")

    run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)

    labels_written = False
    note_written = False
    report_written = False

    if body.labels is not None:
        labels_path = resolved.run_dir / "labels.json"
        labels_path.write_bytes(orjson.dumps(body.labels))
        labels_written = True

    if body.note is not None:
        note_path = resolved.run_dir / "note.md"
        note_path.write_text(body.note, encoding="utf-8")
        note_written = True

    if body.report is not None:
        report_path = resolved.run_dir / f"{resolved.scenario_name}_report.json"
        await write_report(report=body.report, report_path=report_path)
        report_written = True

    logger.info(
        "Synced metadata for run %s: labels=%s note=%s report=%s",
        run_id,
        labels_written,
        note_written,
        report_written,
    )

    return SyncMetadataResponse(
        run_id=run_id,
        labels_written=labels_written,
        note_written=note_written,
        report_written=report_written,
    )
