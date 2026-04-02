"""FastAPI router for simulation run endpoints, including SSE event streaming."""

import logging
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from schmidt.eval_manifest import read_eval_manifest
from schmidt.models.event import RunStatus
from schmidt.scenarios import SCENARIO_REGISTRY
from schmidt.server.response_models import (
    LaunchStatus,
    RunDetailResponse,
    RunListResponse,
    SSEEvent,
    StartEvaluationRequest,
    StartEvaluationResponse,
)
from schmidt.server.run_detail_reader import load_run_detail
from schmidt.server.run_discovery import discover_runs
from schmidt.stream_manifest import delete_manifest, read_manifest
from schmidt.token_pricing import list_providers

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


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: str, request: Request) -> None:
    """Delete a simulation run and all its files."""
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)

    matching = [s for s in summaries if s.run_id == run_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Run not found")

    run_dir = Path(matching[0].run_dir)
    shutil.rmtree(run_dir)
    logger.info("Deleted run directory: %s", run_dir)


@router.post("/runs/{run_id}/stop", status_code=204)
async def stop_run(run_id: str, request: Request) -> None:
    """Stop a running simulation by sending SIGTERM to its process."""
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)

    matching = [s for s in summaries if s.run_id == run_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Run not found")

    run_dir = Path(matching[0].run_dir)
    manifest = read_manifest(run_dir=run_dir)
    if manifest is None:
        raise HTTPException(status_code=409, detail="Simulation is not running")

    try:
        os.kill(manifest.pid, signal.SIGTERM)
        logger.info("Sent SIGTERM to simulation PID %d for run %s", manifest.pid, run_id)
    except ProcessLookupError:
        logger.info("Simulation PID %d already dead for run %s", manifest.pid, run_id)

    delete_manifest(run_dir=run_dir)


@router.post(
    "/runs/{run_id}/evaluate",
    response_model=StartEvaluationResponse,
)
async def start_evaluation(
    run_id: str,
    body: StartEvaluationRequest,
    request: Request,
) -> StartEvaluationResponse:
    """Launch an evaluation subprocess for a completed simulation run.

    Validates that the run exists and is complete, that no evaluation is
    already in progress, and that the requested evaluators and provider
    are valid. Launches ``python -m schmidt evaluate`` as a detached
    background process.
    """
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)

    matching = [s for s in summaries if s.run_id == run_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Run not found")

    run_summary = matching[0]

    finished_statuses = {RunStatus.SCENARIO_COMPLETE, RunStatus.ERROR}
    if run_summary.status not in finished_statuses:
        raise HTTPException(
            status_code=422,
            detail="Evaluation requires a completed or errored run",
        )

    run_dir = Path(run_summary.run_dir)
    if read_eval_manifest(run_dir=run_dir) is not None:
        raise HTTPException(
            status_code=409,
            detail="An evaluation is already in progress for this run",
        )

    if body.provider not in list_providers():
        raise HTTPException(
            status_code=422,
            detail=f"Unknown provider: {body.provider}",
        )

    scenario_cls = SCENARIO_REGISTRY.get(run_summary.scenario_name)
    if scenario_cls is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown scenario: {run_summary.scenario_name}",
        )

    available = scenario_cls.get_available_evaluator_names()
    for name in body.evaluators:
        if name not in available:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown evaluator '{name}'. Available: {', '.join(available)}",
            )

    cmd = [
        sys.executable,
        "-m",
        "schmidt",
        "evaluate",
        run_summary.scenario_name,
        "--run-dir",
        str(run_dir),
        "--evaluators",
        ",".join(body.evaluators),
        "--model",
        body.model,
        "--provider",
        body.provider,
    ]

    logger.info("Launching evaluation: %s", " ".join(cmd))

    try:
        eval_log = run_dir / "eval_stdout.log"
        with open(eval_log, "w") as log_file:
            subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except Exception:
        logger.exception("Failed to launch evaluation subprocess")
        raise HTTPException(
            status_code=500,
            detail="Failed to launch evaluation subprocess",
        )

    return StartEvaluationResponse(status=LaunchStatus.STARTED)


async def _proxy_simulation_sse(
    host: str,
    port: int,
) -> AsyncGenerator[bytes, None]:
    """Proxy SSE events from a running simulation's embedded server.

    Connects to the simulation's SSE endpoint via httpx and re-emits
    each chunk as raw bytes.
    """
    url = f"http://{host}:{port}/events"

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                method="GET",
                url=url,
                timeout=None,
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk
    except httpx.ConnectError:
        logger.exception(
            "Failed to connect to simulation server at %s:%d",
            host,
            port,
        )
    except httpx.HTTPError:
        logger.exception(
            "HTTP error proxying simulation SSE from %s:%d",
            host,
            port,
        )


@router.get(
    "/runs/{run_id}/events",
    responses={
        200: {
            "description": "SSE event stream. Each SSE frame has an `event` field matching "
            "the event_type discriminator and a `data` field containing the JSON payload.",
            "model": SSEEvent,
        },
    },
)
async def stream_run_events(run_id: str, request: Request) -> StreamingResponse:
    """Stream simulation events as Server-Sent Events.

    Only available for live simulations (detected via stream.json manifest).
    Proxies SSE from the simulation's embedded server. Returns 404 if the
    run is not found, and 409 if the simulation is not currently running.

    The SSE ``data`` field of each frame contains a JSON object conforming to
    one of the SSEEvent union members, discriminated by the ``event_type`` field.
    """
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)
    matching = [s for s in summaries if s.run_id == run_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Run not found")

    run_dir = Path(matching[0].run_dir)
    manifest = read_manifest(run_dir=run_dir)
    if manifest is None:
        raise HTTPException(status_code=409, detail="Simulation is not running")

    logger.debug(
        "Proxying SSE from simulation server at %s:%d for run %s",
        manifest.host,
        manifest.port,
        run_id,
    )

    return StreamingResponse(
        content=_proxy_simulation_sse(host=manifest.host, port=manifest.port),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
