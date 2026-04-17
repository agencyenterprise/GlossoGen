"""FastAPI router for exporting simulation runs as PDF documents."""

import asyncio
import logging
from pathlib import Path

import weasyprint  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from schmidt.server.pdf.export_data import build_pdf_export_data
from schmidt.server.pdf.html_renderer import render_pdf_html
from schmidt.server.runs.detail_reader import load_run_detail
from schmidt.server.runs.discovery import resolve_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _generate_pdf_bytes(html: str) -> bytes:
    """Convert an HTML string to PDF bytes using weasyprint.

    This is a synchronous CPU-bound operation, intended to be called
    via asyncio.to_thread() to avoid blocking the event loop.
    """
    result: bytes | None = weasyprint.HTML(string=html).write_pdf()
    if result is None:
        raise RuntimeError("weasyprint.write_pdf() returned None")
    return result


@router.get(
    "/runs/{run_id}/export/pdf",
    responses={
        200: {
            "description": "PDF document of the simulation run.",
            "content": {"application/pdf": {}},
        },
    },
)
async def export_run_pdf(
    run_id: str,
    request: Request,
    channel_id: str | None = Query(default=None),
) -> Response:
    """Export a simulation run as a formatted PDF document.

    Generates a PDF containing messages, reasoning, and tool calls
    grouped by round and turn. Optionally filters to a single channel.
    """
    runs_dir: Path = request.app.state.runs_dir
    try:
        resolved = await resolve_run(runs_dir=runs_dir, run_id=run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")

    log_path = resolved.run_dir / f"{resolved.scenario_name}.jsonl"

    run_detail = await load_run_detail(log_path=log_path)

    if channel_id is not None and channel_id not in run_detail.channel_ids:
        raise HTTPException(status_code=404, detail="Channel not found in this run")

    export_data = build_pdf_export_data(
        run_detail=run_detail,
        channel_id=channel_id,
    )
    html = render_pdf_html(export_data=export_data)
    pdf_bytes = await asyncio.to_thread(_generate_pdf_bytes, html)

    run_id_short = run_id[:8]
    if channel_id is not None:
        filename = f"{resolved.scenario_name}_{channel_id}_{run_id_short}.pdf"
    else:
        filename = f"{resolved.scenario_name}_{run_id_short}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
