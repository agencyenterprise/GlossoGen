"""FastAPI router for scenario discovery and launching new simulation runs.

Provides endpoints to list available scenarios with their knobs files,
read knobs file contents, and start a new simulation as a background subprocess.
"""

import logging
from pathlib import Path

import orjson
from fastapi import APIRouter, HTTPException, Request

from schmidt.scenario_registry import SCENARIO_REGISTRY
from schmidt.server.response_models import LaunchStatus
from schmidt.server.run_launcher import launch_simulation
from schmidt.server.runs.lookup import get_identity
from schmidt.server.scenarios.models import (
    AgentRoleInfo,
    AgentRolesRequest,
    AgentRolesResponse,
    KnobsContentResponse,
    ModelInfo,
    ScenarioInfo,
    ScenariosResponse,
    StartRunRequest,
    StartRunResponse,
)
from schmidt.token_pricing import list_models, list_providers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")

_SCENARIOS_BASE = Path(__file__).resolve().parent.parent.parent / "scenarios"


def _list_knobs_files(scenario_name: str) -> list[str]:
    """Return sorted knobs filenames (without .json extension) for a scenario."""
    scenario_dir = _SCENARIOS_BASE / scenario_name
    if not scenario_dir.is_dir():
        return []
    return sorted(f.stem for f in scenario_dir.glob("knobs_*.json"))


def _resolve_knobs_path(scenario_name: str, knobs_name: str) -> Path:
    """Resolve a knobs name (without .json) to its full filesystem path.

    Validates that the file exists and belongs to the scenario directory.
    Raises HTTPException if not found.
    """
    knobs_path = _SCENARIOS_BASE / scenario_name / f"{knobs_name}.json"
    if not knobs_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Knobs file not found: {knobs_name}",
        )
    return knobs_path


@router.get("/scenarios", response_model=ScenariosResponse)
async def list_scenarios() -> ScenariosResponse:
    """List all available scenarios with their knobs files and supported providers."""
    scenarios: list[ScenarioInfo] = []
    for name in sorted(SCENARIO_REGISTRY.keys()):
        knobs_files = _list_knobs_files(scenario_name=name)
        scenario_cls = SCENARIO_REGISTRY[name]
        metrics = scenario_cls.get_available_metric_names()
        scenarios.append(
            ScenarioInfo(
                scenario_name=name,
                knobs_files=knobs_files,
                available_metrics=metrics,
            )
        )
    models = [
        ModelInfo(model_prefix=prefix, provider=provider) for prefix, provider in list_models()
    ]
    providers = list_providers()
    return ScenariosResponse(scenarios=scenarios, models=models, providers=providers)


@router.get(
    "/scenarios/{scenario_name}/knobs/{knobs_name}",
    response_model=KnobsContentResponse,
)
async def get_knobs_content(scenario_name: str, knobs_name: str) -> KnobsContentResponse:
    """Read and return the contents of a knobs JSON file."""
    if scenario_name not in SCENARIO_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_name}")

    knobs_path = _resolve_knobs_path(scenario_name=scenario_name, knobs_name=knobs_name)
    knobs = orjson.loads(knobs_path.read_bytes())
    return KnobsContentResponse(knobs=knobs)


@router.post(
    "/scenarios/{scenario_name}/agents",
    response_model=AgentRolesResponse,
)
async def get_agent_roles(scenario_name: str, body: AgentRolesRequest) -> AgentRolesResponse:
    """Return the agent IDs, display names, and channels for the given knobs.

    The ``channels`` field is populated by instantiating the scenario
    with the supplied knobs and reading each ``AgentConfig.channel_ids``;
    the FE phase-builder uses this to render per-agent visibility
    controls. Returns an empty channel list per agent if scenario
    instantiation fails (e.g. invalid knobs) so the FE can still show
    role names while the user fixes the knobs.
    """
    if scenario_name not in SCENARIO_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_name}")

    scenario_cls = SCENARIO_REGISTRY[scenario_name]
    roles = scenario_cls.get_agent_roles(knobs=body.knobs)
    channels_by_agent_id = _resolve_channels_by_agent(
        scenario_name=scenario_name,
        knobs=body.knobs,
    )
    return AgentRolesResponse(
        agents=[
            AgentRoleInfo(
                agent_id=r.agent_id,
                role_name=r.role_name,
                channels=channels_by_agent_id.get(r.agent_id, []),
            )
            for r in roles
        ]
    )


def _resolve_channels_by_agent(
    scenario_name: str,
    knobs: dict[str, object] | None,
) -> dict[str, list[str]]:
    """Instantiate the scenario with the given knobs and map agent_id -> channel_ids.

    Returns an empty dict if instantiation fails for any reason; the
    caller falls back to empty channel lists per agent.
    """
    scenario_cls = SCENARIO_REGISTRY[scenario_name]
    try:
        scenario = scenario_cls.create_from_config(config=knobs or {})
        agents = scenario.get_agents(default_model="placeholder", default_provider="anthropic")
    except Exception:
        logger.exception("Failed to resolve channels for scenario %s", scenario_name)
        return {}
    return {agent.agent_id: list(agent.channel_ids) for agent in agents}


@router.post("/runs/start", response_model=StartRunResponse)
async def start_run(body: StartRunRequest, request: Request) -> StartRunResponse:
    """Launch a new simulation as a background subprocess."""
    runs_dir: Path = request.app.state.runs_dir

    if body.scenario_name not in SCENARIO_REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown scenario: {body.scenario_name}",
        )

    available_knobs = _list_knobs_files(scenario_name=body.scenario_name)
    needs_knobs = len(available_knobs) > 0

    if needs_knobs and not body.knobs:
        raise HTTPException(
            status_code=422,
            detail="knobs is required for this scenario",
        )

    scenario_cls = SCENARIO_REGISTRY[body.scenario_name]
    identity = get_identity(request=request)

    try:
        launch_simulation(
            scenario_name=body.scenario_name,
            model=body.model,
            provider=body.provider,
            scenario_cls=scenario_cls,
            knobs=body.knobs,
            runs_dir=runs_dir,
            group_slug=identity.active_group_slug,
        )
    except (SystemExit, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid run configuration: {exc}",
        ) from exc
    except Exception:
        logger.exception("Failed to launch simulation subprocess")
        raise HTTPException(
            status_code=500,
            detail="Failed to launch simulation subprocess",
        )

    return StartRunResponse(status=LaunchStatus.STARTED)
