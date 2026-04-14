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
import orjson
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from schmidt.eval_manifest import read_eval_manifest
from schmidt.models.event import RunStatus, SimulationEnded
from schmidt.scenarios import SCENARIO_REGISTRY
from schmidt.server.response_models import LaunchStatus
from schmidt.server.runs.detail_reader import load_run_detail
from schmidt.server.runs.discovery import discover_runs
from schmidt.server.runs.models import (
    AllLabelsResponse,
    NoteResponse,
    RunDetailResponse,
    RunListResponse,
    SSEEvent,
    StartEvaluationRequest,
    StartEvaluationResponse,
    UpdateLabelsRequest,
    UpdateLabelsResponse,
    UpdateNoteRequest,
    UpdateNoteResponse,
)
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
    """Stop the simulation if still running, then delete the run directory."""
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)

    matching = [s for s in summaries if s.run_id == run_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Run not found")

    run_dir = Path(matching[0].run_dir)

    manifest = read_manifest(run_dir=run_dir)
    if manifest is not None:
        try:
            os.kill(manifest.pid, signal.SIGTERM)
            logger.info("Sent SIGTERM to simulation PID %d before deleting run %s", manifest.pid, run_id)
        except ProcessLookupError:
            logger.info("Simulation PID %d already dead for run %s", manifest.pid, run_id)
        delete_manifest(run_dir=run_dir)

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

    run_summary = matching[0]
    run_dir = Path(run_summary.run_dir)
    manifest = read_manifest(run_dir=run_dir)
    if manifest is None:
        raise HTTPException(status_code=409, detail="Simulation is not running")

    try:
        os.kill(manifest.pid, signal.SIGTERM)
        logger.info("Sent SIGTERM to simulation PID %d for run %s", manifest.pid, run_id)
    except ProcessLookupError:
        logger.info("Simulation PID %d already dead for run %s", manifest.pid, run_id)

    delete_manifest(run_dir=run_dir)

    _append_killed_event(
        run_dir=run_dir,
        scenario_name=run_summary.scenario_name,
        total_messages=run_summary.total_messages,
        total_cost_usd=run_summary.total_cost_usd,
    )


def _append_killed_event(
    run_dir: Path,
    scenario_name: str,
    total_messages: int,
    total_cost_usd: float,
) -> None:
    """Append a SimulationEnded event with reason=killed to the JSONL log."""
    event = SimulationEnded(
        reason=RunStatus.KILLED,
        total_messages=total_messages,
        total_cost_usd=total_cost_usd,
    )
    jsonl_path = run_dir / f"{scenario_name}.jsonl"
    with open(jsonl_path, "ab") as f:
        f.write(orjson.dumps(event.model_dump(mode="json")) + b"\n")
    logger.info("Appended killed event to %s", jsonl_path)


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

    finished_statuses = {RunStatus.SCENARIO_COMPLETE, RunStatus.ERROR, RunStatus.KILLED}
    if run_summary.status not in finished_statuses:
        raise HTTPException(
            status_code=422,
            detail="Evaluation requires a completed, errored, or killed run",
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


async def _resolve_run_dir(run_id: str, request: Request) -> Path:
    """Resolve a run_id to its directory path, raising 404 if not found."""
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)
    matching = [s for s in summaries if s.run_id == run_id]
    if not matching:
        raise HTTPException(status_code=404, detail="Run not found")
    return Path(matching[0].run_dir)


# ---------------------------------------------------------------------------
# Labels and notes endpoints
# ---------------------------------------------------------------------------


@router.put("/runs/{run_id}/labels", response_model=UpdateLabelsResponse)
async def update_labels(
    run_id: str,
    body: UpdateLabelsRequest,
    request: Request,
) -> UpdateLabelsResponse:
    """Set labels for a simulation run, replacing any existing labels."""
    run_dir = await _resolve_run_dir(run_id=run_id, request=request)
    labels_path = run_dir / "labels.json"
    labels_path.write_bytes(orjson.dumps(body.labels))
    logger.info("Updated labels for run %s: %s", run_id, body.labels)
    return UpdateLabelsResponse(labels=body.labels)


@router.put("/runs/{run_id}/note", response_model=UpdateNoteResponse)
async def update_note(
    run_id: str,
    body: UpdateNoteRequest,
    request: Request,
) -> UpdateNoteResponse:
    """Set or update the note for a simulation run."""
    run_dir = await _resolve_run_dir(run_id=run_id, request=request)
    note_path = run_dir / "note.md"
    note_path.write_text(body.content, encoding="utf-8")
    logger.info("Updated note for run %s (%d chars)", run_id, len(body.content))
    return UpdateNoteResponse(content=body.content)


@router.get("/runs/{run_id}/note", response_model=NoteResponse)
async def get_note(run_id: str, request: Request) -> NoteResponse:
    """Get the note content for a simulation run."""
    run_dir = await _resolve_run_dir(run_id=run_id, request=request)
    note_path = run_dir / "note.md"
    if not note_path.exists():
        return NoteResponse(content=None)
    content = note_path.read_text(encoding="utf-8")
    return NoteResponse(content=content)


@router.get("/labels", response_model=AllLabelsResponse)
async def list_all_labels(request: Request) -> AllLabelsResponse:
    """Get all unique labels across all simulation runs."""
    runs_dir: Path = request.app.state.runs_dir
    summaries = await discover_runs(runs_dir=runs_dir)
    seen: dict[str, None] = {}
    for summary in summaries:
        for label in summary.labels:
            if label not in seen:
                seen[label] = None
    return AllLabelsResponse(labels=sorted(seen))
