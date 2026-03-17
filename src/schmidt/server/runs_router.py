"""FastAPI router for simulation run endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, Request

from schmidt.server.response_models import RunListResponse
from schmidt.server.run_discovery import discover_runs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/runs", response_model=RunListResponse)
async def list_runs(request: Request) -> RunListResponse:
    """List all discovered simulation runs."""
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)
    return RunListResponse(runs=summaries)
