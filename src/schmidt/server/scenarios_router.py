"""FastAPI router for scenario discovery and launching new simulation runs.

Provides endpoints to list available scenarios with their knobs files,
read knobs file contents, and start a new simulation as a background subprocess.
"""

import asyncio
import logging
import socket
import subprocess
import sys
from pathlib import Path

import orjson
from fastapi import APIRouter, HTTPException, Request

from schmidt.run_repository import claim_run_dir
from schmidt.scenarios import SCENARIO_REGISTRY
from schmidt.server.response_models import (
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


@router.get("/scenarios", response_model=ScenariosResponse)
async def list_scenarios() -> ScenariosResponse:
    """List all available scenarios with their knobs files and supported providers."""
    scenarios = []
    for name in sorted(SCENARIO_REGISTRY.keys()):
        knobs_files = _list_knobs_files(scenario_name=name)
        scenarios.append(ScenarioInfo(scenario_name=name, knobs_files=knobs_files))
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


async def _wait_for_run_id(
    run_dir: Path,
    scenario_name: str,
    timeout_seconds: float,
) -> str:
    """Poll the JSONL file until the simulation_started event appears.

    Returns the run_id from the first event. Raises HTTPException if the
    event does not appear within the timeout.
    """
    jsonl_path = run_dir / f"{scenario_name}.jsonl"
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_seconds

    while loop.time() < deadline:
        if jsonl_path.exists():
            raw = jsonl_path.read_bytes()
            first_line = raw.split(b"\n")[0].strip()
            if first_line:
                event = orjson.loads(first_line)
                if event.get("event_type") == "simulation_started":
                    run_id: str = event["run_id"]
                    return run_id
        await asyncio.sleep(0.3)

    raise HTTPException(
        status_code=500,
        detail="Simulation failed to start within timeout",
    )


@router.post("/runs/start", response_model=StartRunResponse)
async def start_run(body: StartRunRequest, request: Request) -> StartRunResponse:
    """Launch a new simulation as a background subprocess.

    Validates inputs, creates a run directory, writes the knobs dict to a
    temporary JSON file, builds the CLI command, and waits for the subprocess
    to write its first event before returning the run_id.
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

    scenario_dir = _SCENARIOS_BASE / body.scenario_name
    run_dir = claim_run_dir(runs_dir=runs_dir, scenario_name=body.scenario_name)
    mcp_port = _find_free_port()
    stdout_log = run_dir / f"{body.scenario_name}_stdout.log"

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

    if body.knobs:
        knobs_path = run_dir / "knobs.json"
        knobs_path.write_bytes(orjson.dumps(body.knobs))
        cmd.extend(["--knobs", str(knobs_path)])

    if body.scenario_name == "persuasion_debate":
        questions_path = scenario_dir / "questions.json"
        cmd.extend(["--questions", str(questions_path)])

    logger.info("Launching new simulation: %s", " ".join(cmd))

    with open(stdout_log, "w") as log_file:
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    run_id = await _wait_for_run_id(
        run_dir=run_dir,
        scenario_name=body.scenario_name,
        timeout_seconds=10.0,
    )

    return StartRunResponse(run_id=run_id, run_dir=str(run_dir))
