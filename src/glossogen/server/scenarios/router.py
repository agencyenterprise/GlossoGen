"""FastAPI router for scenario discovery.

Provides endpoints to list available scenarios with their knobs files and
read knobs file contents. Simulation launches happen via the CLI.
"""

import logging
from pathlib import Path

import orjson
from fastapi import APIRouter, HTTPException

from glossogen.scenario_registry import SCENARIO_REGISTRY
from glossogen.server.scenarios.models import (
    KnobsContentResponse,
    ModelInfo,
    ScenarioInfo,
    ScenariosResponse,
)
from glossogen.token_pricing import list_models, list_providers

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
