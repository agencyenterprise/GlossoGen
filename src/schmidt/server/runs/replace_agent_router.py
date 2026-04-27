"""FastAPI router for replacing one agent in a finished simulation run.

Thin HTTP wrapper around ``schmidt.replace_agent.replace_agent_in_run``.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from schmidt.replace_agent import ReplaceAgentRequest as CoreReplaceAgentRequest
from schmidt.replace_agent import replace_agent_in_run
from schmidt.server.runs.discovery import resolve_run
from schmidt.server.runs.models import ReplaceAgentRequest, ReplaceAgentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post(
    "/runs/{scenario}/{run_dir_name}/replace-agent",
    response_model=ReplaceAgentResponse,
)
async def replace_agent(
    scenario: str,
    run_dir_name: str,
    body: ReplaceAgentRequest,
    request: Request,
) -> ReplaceAgentResponse:
    """Replace one agent in a finished run with a fresh agent from a target message.

    The new agent has no message history; every other agent resumes from
    its full reconstructed history. Optionally swaps the replaced agent's
    model/provider.
    """
    try:
        resolved = resolve_run(
            runs_dir=request.app.state.runs_dir,
            scenario_name=scenario,
            run_dir_name=run_dir_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc

    core_request = CoreReplaceAgentRequest(
        source_run_dir=resolved.run_dir,
        scenario_name=resolved.scenario_name,
        round_start=body.round_start,
        replaced_agent_id=body.replaced_agent_id,
        model=body.model,
        provider=body.provider,
        knobs=body.knobs,
        channels_with_visible_history=body.channels_with_visible_history,
        runs_dir=request.app.state.runs_dir,
    )

    try:
        result = await replace_agent_in_run(request=core_request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ReplaceAgentResponse(
        new_run_id=result.new_run_id,
        new_run_dir=str(result.new_run_dir),
    )
