"""FastAPI router for scenario discovery and launching new simulation runs.

Provides endpoints to list available scenarios with their knobs files,
read knobs file contents, and start a new simulation as a background subprocess.
"""

import logging
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import orjson
from fastapi import APIRouter, HTTPException, Request

from schmidt.run_config_validation import validate_run_config
from schmidt.scenarios import SCENARIO_REGISTRY
from schmidt.server.response_models import LaunchStatus
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

router = APIRouter(prefix="/api")

_SCENARIOS_BASE = Path(__file__).resolve().parent.parent / "scenarios"


def _find_free_port() -> int:
    """Find an available TCP port by briefly binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


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


def _build_config_file(
    knobs: dict[str, Any] | None,
) -> Path | None:
    """Build a temporary config file for the subprocess.

    Writes the validated knobs/config payload to a single config file
    under ``--config``.
    """
    config: dict[str, Any] = {}
    if knobs:
        config.update(knobs)

    config_path: Path | None = None
    if config:
        fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="config_")
        os.close(fd)
        config_path = Path(tmp_path)
        config_path.write_bytes(orjson.dumps(config))

    return config_path


@router.get("/scenarios", response_model=ScenariosResponse)
async def list_scenarios() -> ScenariosResponse:
    """List all available scenarios with their knobs files and supported providers."""
    scenarios = []
    for name in sorted(SCENARIO_REGISTRY.keys()):
        knobs_files = _list_knobs_files(scenario_name=name)
        scenario_cls = SCENARIO_REGISTRY[name]
        evaluators = scenario_cls.get_available_evaluator_names()
        scenarios.append(
            ScenarioInfo(
                scenario_name=name,
                knobs_files=knobs_files,
                available_evaluators=evaluators,
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
    """Return the agent IDs and display names for a scenario with the given knobs."""
    if scenario_name not in SCENARIO_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_name}")

    scenario_cls = SCENARIO_REGISTRY[scenario_name]
    roles = scenario_cls.get_agent_roles(knobs=body.knobs)
    return AgentRolesResponse(
        agents=[AgentRoleInfo(agent_id=r.agent_id, role_name=r.role_name) for r in roles]
    )


@router.post("/runs/start", response_model=StartRunResponse)
async def start_run(body: StartRunRequest, request: Request) -> StartRunResponse:
    """Launch a new simulation as a background subprocess.

    Validates inputs, writes knobs/config to a config file,
    and launches the subprocess with ``--config``.
    """
    runs_dir: Path = request.app.state.runs_dir

    if body.scenario_name not in SCENARIO_REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown scenario: {body.scenario_name}",
        )
    if body.provider not in list_providers():
        raise HTTPException(
            status_code=422,
            detail=f"Unknown provider: {body.provider}",
        )

    available_knobs = _list_knobs_files(scenario_name=body.scenario_name)
    needs_knobs = len(available_knobs) > 0

    if needs_knobs and not body.knobs:
        raise HTTPException(
            status_code=422,
            detail="knobs is required for this scenario",
        )

    mcp_port = _find_free_port()

    cmd = [
        sys.executable,
        "-m",
        "schmidt",
        "run",
        body.scenario_name,
        "--model",
        body.model,
        "--provider",
        body.provider,
        "--mcp-port",
        str(mcp_port),
        "--runs-dir",
        str(runs_dir),
    ]

    scenario_cls = SCENARIO_REGISTRY[body.scenario_name]
    raw_scenario_config = dict(body.knobs) if body.knobs is not None else {}

    try:
        validated = validate_run_config(
            scenario_cls=scenario_cls,
            scenario_config=raw_scenario_config,
            default_provider=body.provider,
            valid_providers=set(list_providers()),
        )
    except (SystemExit, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid run configuration: {exc}") from exc

    config_path = _build_config_file(
        knobs=validated.scenario_config,
    )

    if config_path is not None:
        cmd.extend(["--config", str(config_path)])

    logger.info("Launching new simulation: %s", " ".join(cmd))

    try:
        stdout_log = runs_dir / f"{body.scenario_name}_start.log"
        with open(stdout_log, "w") as log_file:
            subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except Exception:
        logger.exception("Failed to launch simulation subprocess")
        raise HTTPException(
            status_code=500,
            detail="Failed to launch simulation subprocess",
        )

    return StartRunResponse(status=LaunchStatus.STARTED)
