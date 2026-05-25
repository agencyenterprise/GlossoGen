"""FastAPI router for round-anchored resume of a finished simulation run.

Thin HTTP wrapper around ``schmidt.replace_agent.replace_agent_in_run``,
called with ``replaced_agent_id=None`` so no agent is restarted; every
agent keeps its full reconstructed history. Knob overrides are merged
onto the source's scenario config to enable post-hoc reconfiguration
(e.g. toggling postmortem, adding scheduled swaps, extending round_count).
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from schmidt.models.event import RunStatus
from schmidt.replace_agent import ReplaceAgentRequest as CoreReplaceAgentRequest
from schmidt.replace_agent import replace_agent_in_run
from schmidt.server.runs.lookup import register_new_run, resolve_run_or_404
from schmidt.server.runs.models import ResumeAtRoundRequest, ResumeAtRoundResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")


@router.post(
    "/runs/{scenario}/{run_dir_name}/resume-at-round",
    response_model=ResumeAtRoundResponse,
)
async def resume_at_round(
    scenario: str,
    run_dir_name: str,
    body: ResumeAtRoundRequest,
    request: Request,
) -> ResumeAtRoundResponse:
    """Clone a finished run at the start of ``round_start`` and resume it.

    No agent is replaced; every agent keeps its full reconstructed history.
    ``body.knobs`` is shallow-merged onto the source's scenario config to
    let callers reconfigure the post-resume simulation.
    """
    resolved = await resolve_run_or_404(
        request=request,
        scenario=scenario,
        run_dir_name=run_dir_name,
    )

    core_request = CoreReplaceAgentRequest(
        source_run_dir=resolved.run_dir,
        scenario_name=resolved.scenario_name,
        round_start=body.round_start,
        rounds_after_swap=body.rounds_after_resume,
        replaced_agent_id=None,
        model=None,
        provider=None,
        knobs=body.knobs,
        channels_with_visible_history=None,
        runs_dir=request.app.state.runs_dir,
    )

    try:
        result = await replace_agent_in_run(request=core_request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await register_new_run(
        request=request,
        scenario=resolved.scenario_name,
        run_dir_name=result.new_run_dir.name,
        status=RunStatus.STARTING.value,
        source_run_scenario=resolved.scenario_name,
        source_run_dir_name=run_dir_name,
    )

    return ResumeAtRoundResponse(
        new_run_id=result.new_run_id,
        new_run_dir=str(result.new_run_dir),
    )
