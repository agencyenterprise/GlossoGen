"""FastAPI router for simulation run endpoints, including SSE event streaming."""

import logging
import os
import signal
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Literal

import httpx
import orjson
from fastapi import APIRouter, HTTPException, Query, Request
from starlette.responses import StreamingResponse

from schmidt.eval_manifest import read_eval_manifest
from schmidt.evaluation.reports.evaluation_report import EvaluationReport, write_report
from schmidt.models.event import RunStatus, SimulationEnded
from schmidt.run_archive import move_run_to_trash
from schmidt.scenario_registry import SCENARIO_REGISTRY
from schmidt.server.response_models import LaunchStatus
from schmidt.server.runs.derived_run_references import build_derived_run_references
from schmidt.server.runs.detail_reader import (
    debug_log_path_for,
    load_debug_logs,
    load_evaluation_report,
    load_run_detail,
)
from schmidt.server.runs.discovery import compose_run_id, scan_jsonl
from schmidt.server.runs.listing import list_all_labels_for_group, list_runs_page_for_group
from schmidt.server.runs.lookup import deregister_run, get_identity, resolve_run_or_404
from schmidt.server.runs.models import (
    AllLabelsResponse,
    DebugLogsResponse,
    EvalLogLine,
    EvalLogsResponse,
    EvalReportResponse,
    NoteResponse,
    RunDetailResponse,
    RunListResponse,
    SSEEvent,
    StartEvaluationRequest,
    StartEvaluationResponse,
    UpdateEvaluationResponse,
    UpdateLabelsRequest,
    UpdateLabelsResponse,
    UpdateNoteRequest,
    UpdateNoteResponse,
)
from schmidt.stream_manifest import delete_manifest, read_manifest
from schmidt.thread_export.export_agent_thread import (
    ThreadExportFormat,
    export_agent_thread_from_run_dir,
)
from schmidt.thread_export.thread_export_models import ThreadExport
from schmidt.token_pricing import list_providers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    request: Request,
    scenario: list[str] | None = Query(default=None),
    contains_agent_id: str | None = None,
    status: RunStatus | None = None,
    labels: list[str] | None = Query(default=None),
    run_id_contains: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> RunListResponse:
    """List one page of simulation runs owned by the active group, newest-first.

    Filters: ``scenario`` keeps runs in any of the listed scenarios (OR
    semantics); ``labels`` keeps runs carrying every listed label (AND
    semantics); ``run_id_contains`` keeps runs whose ``scenario/run_dir_name``
    id contains the substring (case-insensitive); ``status`` restricts to a
    final status; ``contains_agent_id`` keeps runs that registered that agent
    (used by the cross-run replace-agent picker). ``offset``/``limit`` page the
    result; ``total`` is the count matching the filters before paging.
    """
    page = await list_runs_page_for_group(
        request=request,
        scenarios=scenario or [],
        labels=labels or [],
        run_id_contains=run_id_contains,
        status=status,
        contains_agent_id=contains_agent_id,
        offset=offset,
        limit=limit,
    )
    return RunListResponse(runs=page.runs, total=page.total)


@router.get("/runs/{scenario}/{run_dir_name}", response_model=RunDetailResponse)
async def get_run_detail(
    scenario: str,
    run_dir_name: str,
    request: Request,
) -> RunDetailResponse:
    """Get full detail for a specific simulation run."""
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    log_path = resolved.run_dir / f"{resolved.scenario_name}.jsonl"
    identity = get_identity(request=request)
    children = await build_derived_run_references(
        pool=request.app.state.db_pool,
        runs_dir=request.app.state.runs_dir,
        group_id=identity.active_group_id,
        parent_scenario=resolved.scenario_name,
        parent_run_dir_name=run_dir_name,
    )
    return await load_run_detail(log_path=log_path, children=children)


@router.get(
    "/runs/{scenario}/{run_dir_name}/agents/{agent_id}/thread",
    response_model=ThreadExport,
)
async def get_agent_thread_export(
    scenario: str,
    run_dir_name: str,
    agent_id: str,
    request: Request,
    cutoff_round: int | None = Query(default=None, alias="round"),
    output_format: Literal["anthropic", "openai"] | None = Query(default=None, alias="format"),
    include_thinking: bool = Query(default=False),
    flatten_tools: bool = Query(default=False),
) -> ThreadExport:
    """Export one agent's reconstructed thread as a drop-in provider-native request body.

    ``round`` is the exclusive cutoff (rounds ``1..round-1``; omit for the full
    end-of-run thread); ``format`` defaults to the format matching the agent's
    own provider. The returned ``request`` is a ready-to-POST Anthropic/OpenAI
    body — the caller appends their own trailing user message (and ``max_tokens``
    for Anthropic) and sends it to the provider.
    """
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    resolved_format: ThreadExportFormat | None
    if output_format == "anthropic":
        resolved_format = "anthropic_messages"
    elif output_format == "openai":
        resolved_format = "openai_chat"
    else:
        resolved_format = None
    try:
        return await export_agent_thread_from_run_dir(
            run_dir=resolved.run_dir,
            scenario_name=resolved.scenario_name,
            agent_id=agent_id,
            cutoff_round=cutoff_round,
            output_format=resolved_format,
            include_thinking=include_thinking,
            flatten_tools=flatten_tools,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{scenario}/{run_dir_name}/evaluation", response_model=EvalReportResponse | None)
async def get_run_evaluation(
    scenario: str,
    run_dir_name: str,
    request: Request,
) -> EvalReportResponse | None:
    """Return only the evaluation report for a run, or null if it has not been evaluated.

    Lighter than the full run-detail endpoint — used by the runs list to lazy-load
    measurements on hover without pulling messages, reasoning, or tool use.
    """
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    report_path = resolved.run_dir / f"{resolved.scenario_name}_report.json"
    return await load_evaluation_report(report_path=report_path)


@router.get("/runs/{scenario}/{run_dir_name}/eval-logs", response_model=EvalLogsResponse)
async def get_eval_logs(
    scenario: str,
    run_dir_name: str,
    request: Request,
) -> EvalLogsResponse:
    """Return the contents of the evaluation stdout log file."""
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    eval_log_path = resolved.run_dir / "eval_stdout.log"

    if not eval_log_path.exists():
        return EvalLogsResponse(lines=[])

    text = eval_log_path.read_text(encoding="utf-8", errors="replace")
    lines = [EvalLogLine(line_number=i + 1, text=line) for i, line in enumerate(text.splitlines())]
    return EvalLogsResponse(lines=lines)


@router.get("/runs/{scenario}/{run_dir_name}/debug-logs", response_model=DebugLogsResponse)
async def get_debug_logs(
    scenario: str,
    run_dir_name: str,
    request: Request,
) -> DebugLogsResponse:
    """Return the debug log entries for a simulation run."""
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    log_path = resolved.run_dir / f"{resolved.scenario_name}.jsonl"
    debug_path = debug_log_path_for(log_path=log_path, scenario_name=resolved.scenario_name)
    entries = await load_debug_logs(debug_log_path=debug_path)
    return DebugLogsResponse(entries=entries)


@router.delete("/runs/{scenario}/{run_dir_name}", status_code=204)
async def delete_run(scenario: str, run_dir_name: str, request: Request) -> None:
    """Stop the simulation if still running, then move the run directory to trash.

    Reversible: the run's files are moved into ``{runs_dir}/_trash/`` rather
    than removed, so a deletion can be undone by moving the directory back and
    re-registering it. The Postgres index row is deleted so the run no longer
    appears in listings.
    """
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)

    run_dir = resolved.run_dir
    runs_dir: Path = request.app.state.runs_dir

    manifest = read_manifest(run_dir=run_dir)
    if manifest is not None:
        try:
            os.kill(manifest.pid, signal.SIGTERM)
            logger.info(
                "Sent SIGTERM to simulation PID %d before trashing run %s", manifest.pid, run_id
            )
        except ProcessLookupError:
            logger.info("Simulation PID %d already dead for run %s", manifest.pid, run_id)
        delete_manifest(run_dir=run_dir)

    trashed_dir = move_run_to_trash(
        runs_dir=runs_dir, scenario_name=scenario, run_dir_name=run_dir_name
    )
    await deregister_run(request=request, scenario=scenario, run_dir_name=run_dir_name)
    logger.info("Moved run to trash and removed index row: %s -> %s", run_dir, trashed_dir)


@router.post("/runs/{scenario}/{run_dir_name}/stop", status_code=204)
async def stop_run(scenario: str, run_dir_name: str, request: Request) -> None:
    """Stop a running simulation by sending SIGTERM to its process."""
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)

    manifest = read_manifest(run_dir=resolved.run_dir)
    if manifest is None:
        raise HTTPException(status_code=409, detail="Simulation is not running")

    try:
        os.kill(manifest.pid, signal.SIGTERM)
        logger.info("Sent SIGTERM to simulation PID %d for run %s", manifest.pid, run_id)
    except ProcessLookupError:
        logger.info("Simulation PID %d already dead for run %s", manifest.pid, run_id)

    delete_manifest(run_dir=resolved.run_dir)

    jsonl_path = resolved.run_dir / f"{resolved.scenario_name}.jsonl"
    scan = await scan_jsonl(file_path=jsonl_path)
    _append_killed_event(
        run_dir=resolved.run_dir,
        scenario_name=resolved.scenario_name,
        total_messages=scan.message_count,
        total_cost_usd=scan.cost_usd,
        round_number=scan.current_round,
    )


def _append_killed_event(
    run_dir: Path,
    scenario_name: str,
    total_messages: int,
    total_cost_usd: float,
    round_number: int,
) -> None:
    """Append a SimulationEnded event with reason=killed to the JSONL log."""
    event = SimulationEnded(
        reason=RunStatus.KILLED,
        total_messages=total_messages,
        total_cost_usd=total_cost_usd,
        round_number=round_number,
    )
    jsonl_path = run_dir / f"{scenario_name}.jsonl"
    with open(jsonl_path, "ab") as f:
        f.write(orjson.dumps(event.model_dump(mode="json")) + b"\n")
    logger.info("Appended killed event to %s", jsonl_path)


@router.post(
    "/runs/{scenario}/{run_dir_name}/evaluate",
    response_model=StartEvaluationResponse,
)
async def start_evaluation(
    scenario: str,
    run_dir_name: str,
    body: StartEvaluationRequest,
    request: Request,
) -> StartEvaluationResponse:
    """Launch an evaluation subprocess for a completed simulation run.

    Validates that the run exists and is complete, that no evaluation is
    already in progress, and that the requested metrics and provider
    are valid. Launches ``python -m schmidt evaluate`` as a detached
    background process. Rejected with 403 when evaluations are disabled
    via the ``ENABLE_EVALUATIONS`` env var.
    """
    if not request.app.state.feature_flags.evaluations_enabled:
        raise HTTPException(
            status_code=403,
            detail="Evaluations are disabled on this server",
        )

    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )

    run_dir = resolved.run_dir
    jsonl_path = run_dir / f"{resolved.scenario_name}.jsonl"
    scan = await scan_jsonl(file_path=jsonl_path)

    if scan.last_event is not None:
        status = scan.last_event.reason
    else:
        manifest = read_manifest(run_dir=run_dir)
        if manifest is not None:
            status = RunStatus.IN_PROGRESS
        else:
            status = RunStatus.ERROR

    finished_statuses = {RunStatus.SCENARIO_COMPLETE, RunStatus.ERROR, RunStatus.KILLED}
    if status not in finished_statuses:
        raise HTTPException(
            status_code=422,
            detail="Evaluation requires a completed, errored, or killed run",
        )

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

    scenario_cls = SCENARIO_REGISTRY.get(resolved.scenario_name)
    if scenario_cls is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown scenario: {resolved.scenario_name}",
        )

    available = scenario_cls.get_available_metric_names()
    for name in body.metrics:
        if name not in available:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown metric '{name}'. Available: {', '.join(available)}",
            )

    cmd = [
        sys.executable,
        "-m",
        "schmidt",
        "evaluate",
        resolved.scenario_name,
        "--run-dir",
        str(run_dir),
        "--metrics",
        ",".join(body.metrics),
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
            status_code=503,
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
    "/runs/{scenario}/{run_dir_name}/events",
    responses={
        200: {
            "description": "SSE event stream. Each SSE frame has an `event` field matching "
            "the event_type discriminator and a `data` field containing the JSON payload.",
            "model": SSEEvent,
        },
    },
)
async def stream_run_events(
    scenario: str,
    run_dir_name: str,
    request: Request,
) -> StreamingResponse:
    """Stream simulation events as Server-Sent Events.

    Only available for live simulations (detected via stream.json manifest).
    Proxies SSE from the simulation's embedded server. Returns 404 if the
    run is not found, and 409 if the simulation is not currently running.

    The SSE ``data`` field of each frame contains a JSON object conforming to
    one of the SSEEvent union members, discriminated by the ``event_type`` field.
    """
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)

    manifest = read_manifest(run_dir=resolved.run_dir)
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


# ---------------------------------------------------------------------------
# Labels and notes endpoints
# ---------------------------------------------------------------------------


@router.put("/runs/{scenario}/{run_dir_name}/labels", response_model=UpdateLabelsResponse)
async def update_labels(
    scenario: str,
    run_dir_name: str,
    body: UpdateLabelsRequest,
    request: Request,
) -> UpdateLabelsResponse:
    """Set labels for a simulation run, replacing any existing labels."""
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)
    labels_path = resolved.run_dir / "labels.json"
    labels_path.write_bytes(orjson.dumps(body.labels))
    logger.info("Updated labels for run %s: %s", run_id, body.labels)
    return UpdateLabelsResponse(labels=body.labels)


@router.put("/runs/{scenario}/{run_dir_name}/note", response_model=UpdateNoteResponse)
async def update_note(
    scenario: str,
    run_dir_name: str,
    body: UpdateNoteRequest,
    request: Request,
) -> UpdateNoteResponse:
    """Set or update the note for a simulation run."""
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)
    note_path = resolved.run_dir / "note.md"
    note_path.write_text(body.content, encoding="utf-8")
    logger.info("Updated note for run %s (%d chars)", run_id, len(body.content))
    return UpdateNoteResponse(content=body.content)


@router.get("/runs/{scenario}/{run_dir_name}/note", response_model=NoteResponse)
async def get_note(scenario: str, run_dir_name: str, request: Request) -> NoteResponse:
    """Get the note content for a simulation run."""
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    note_path = resolved.run_dir / "note.md"
    if not note_path.exists():
        return NoteResponse(content=None)
    content = note_path.read_text(encoding="utf-8")
    return NoteResponse(content=content)


@router.put(
    "/runs/{scenario}/{run_dir_name}/evaluation",
    response_model=UpdateEvaluationResponse,
)
async def update_evaluation(
    scenario: str,
    run_dir_name: str,
    body: EvaluationReport,
    request: Request,
) -> UpdateEvaluationResponse:
    """Replace the saved evaluation report for a simulation run on disk.

    Used by ``schmidt sync-metadata-to-prod`` to push freshly-evaluated
    measurements onto runs that already exist on the remote without
    re-uploading the full bundle. The PUT is a full replace — every
    existing measurement is overwritten with the body.
    """
    resolved = await resolve_run_or_404(
        request=request, scenario=scenario, run_dir_name=run_dir_name
    )
    run_id = compose_run_id(scenario_name=scenario, run_dir_name=run_dir_name)
    report_path = resolved.run_dir / f"{resolved.scenario_name}_report.json"
    await write_report(report=body, report_path=report_path)
    logger.info(
        "Updated evaluation report for run %s (%d measurements)",
        run_id,
        len(body.measurements),
    )
    return UpdateEvaluationResponse(
        run_id=run_id,
        measurement_count=len(body.measurements),
    )


@router.get("/labels", response_model=AllLabelsResponse)
async def list_all_labels(request: Request) -> AllLabelsResponse:
    """Get all unique labels across the active group's simulation runs."""
    labels = await list_all_labels_for_group(request=request)
    return AllLabelsResponse(labels=labels)
