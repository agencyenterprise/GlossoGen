"""FastAPI router for simulation run endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from schmidt.server.response_models import RunDetailResponse, RunListResponse
from schmidt.server.run_detail_reader import load_run_detail
from schmidt.server.run_discovery import discover_runs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.get("/runs", response_model=RunListResponse)
async def list_runs(request: Request) -> RunListResponse:
    """List all discovered simulation runs."""
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)
    return RunListResponse(runs=summaries)


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run_detail(run_id: str, request: Request) -> RunDetailResponse:
    """Get full detail for a specific simulation run."""
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)

    matching = [s for s in summaries if s.run_id == run_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Run not found")

    run_summary = matching[0]
    run_dir = Path(run_summary.run_dir)
    log_path = run_dir / f"{run_summary.scenario_name}.jsonl"

    return await load_run_detail(log_path=log_path)
