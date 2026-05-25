"""FastAPI router for cross-run replace-agent operations.

Thin HTTP wrapper around
``schmidt.cross_run_replace_agent.cross_run_replace_agent_in_run``.
Imports one agent from a different completed run (Sim B) into a target
run (Sim A) at a chosen round boundary, with the imported agent
retaining its full pydantic-ai history (text, thinking, tool calls).
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from schmidt.cross_run_replace_agent import CrossRunReplaceAgentRequest as CoreRequest
from schmidt.cross_run_replace_agent import cross_run_replace_agent_in_run
from schmidt.evaluation.log_reader import load_events
from schmidt.models.event import AgentRegistered, RoundAdvanced, RunStatus
from schmidt.server.runs.lookup import register_new_run, resolve_run_or_404
from schmidt.server.runs.models import CrossRunReplaceAgentRequest, CrossRunReplaceAgentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")


def _split_run_id(run_id: str) -> tuple[str, str]:
    """Split a canonical ``<scenario>/<run_dir>`` identifier."""
    parts = run_id.split("/", maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Invalid run id: {run_id!r} (expected '<scenario>/<run_dir>')")
    return parts[0], parts[1]


async def _read_source_b_model(
    source_b_run_dir: Path,
    scenario_name: str,
    replaced_agent_id: str,
) -> tuple[str, str]:
    """Read source B's ``AgentRegistered`` for the replaced agent.

    Returns ``(model, provider)``. Raises ``HTTPException`` 422 when the
    agent is missing in source B so the caller gets a clear error
    before the orchestrator runs.
    """
    log_path = source_b_run_dir / f"{scenario_name}.jsonl"
    events = await load_events(log_path=log_path)
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id == replaced_agent_id:
            return event.model, event.provider
    raise HTTPException(
        status_code=422,
        detail=(
            f"Agent {replaced_agent_id!r} not found in source B run "
            f"{source_b_run_dir.name}"
        ),
    )


async def _read_source_b_max_round(
    source_b_run_dir: Path,
    scenario_name: str,
) -> int:
    """Return the highest ``RoundAdvanced.round_number`` observed in source B.

    Used to clamp the default ``source_b_round_end`` to source B's actual
    reach. Raises ``HTTPException`` 422 if source B has no rounds.
    """
    log_path = source_b_run_dir / f"{scenario_name}.jsonl"
    events = await load_events(log_path=log_path)
    max_round = 0
    for event in events:
        if isinstance(event, RoundAdvanced) and event.round_number > max_round:
            max_round = event.round_number
    if max_round == 0:
        raise HTTPException(
            status_code=422,
            detail=f"Source B run {source_b_run_dir.name} has no RoundAdvanced events",
        )
    return max_round


@router.post(
    "/runs/{scenario}/{run_dir_name}/cross-run-replace-agent",
    response_model=CrossRunReplaceAgentResponse,
)
async def cross_run_replace_agent(
    scenario: str,
    run_dir_name: str,
    body: CrossRunReplaceAgentRequest,
    request: Request,
) -> CrossRunReplaceAgentResponse:
    """Import an agent from one finished run into another at a chosen round boundary.

    The imported agent keeps its full pydantic-ai history (text,
    thinking, tool calls) up to ``source_b_round_end`` of the source
    run, then re-enters the target run at ``round_start``. Same
    scenario and same ``agent_id`` only.
    """
    runs_dir: Path = request.app.state.runs_dir

    source_a = await resolve_run_or_404(
        request=request,
        scenario=scenario,
        run_dir_name=run_dir_name,
    )

    try:
        source_b_scenario, source_b_dir_name = _split_run_id(run_id=body.source_b_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if source_b_scenario != scenario:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Scenario mismatch: target run is {scenario!r}, "
                f"source_b_run_id is {source_b_scenario!r}"
            ),
        )

    source_b = await resolve_run_or_404(
        request=request,
        scenario=source_b_scenario,
        run_dir_name=source_b_dir_name,
    )

    if (body.model is None) != (body.provider is None):
        raise HTTPException(
            status_code=422,
            detail="model and provider must be provided together (both or neither)",
        )

    if body.source_b_round_end is None:
        source_b_max_round = await _read_source_b_max_round(
            source_b_run_dir=source_b.run_dir,
            scenario_name=source_a.scenario_name,
        )
        source_b_round_end = min(body.round_start - 1, source_b_max_round)
    else:
        source_b_round_end = body.source_b_round_end

    if body.model is None or body.provider is None:
        model, provider = await _read_source_b_model(
            source_b_run_dir=source_b.run_dir,
            scenario_name=source_a.scenario_name,
            replaced_agent_id=body.replaced_agent_id,
        )
    else:
        model = body.model
        provider = body.provider

    core_request = CoreRequest(
        source_a_run_dir=source_a.run_dir,
        source_b_run_dir=source_b.run_dir,
        scenario_name=source_a.scenario_name,
        round_start=body.round_start,
        source_b_round_end=source_b_round_end,
        rounds_after_swap=body.rounds_after_swap,
        replaced_agent_id=body.replaced_agent_id,
        model=model,
        provider=provider,
        knobs=body.knobs,
        channels_with_visible_history=body.channels_with_visible_history,
        runs_dir=runs_dir,
    )

    try:
        result = await cross_run_replace_agent_in_run(request=core_request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await register_new_run(
        request=request,
        scenario=source_a.scenario_name,
        run_dir_name=result.new_run_dir.name,
        status=RunStatus.STARTING.value,
        source_run_scenario=source_a.scenario_name,
        source_run_dir_name=run_dir_name,
    )

    return CrossRunReplaceAgentResponse(
        new_run_id=result.new_run_id,
        new_run_dir=str(result.new_run_dir),
    )
