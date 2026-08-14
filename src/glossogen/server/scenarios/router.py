"""FastAPI router for scenario discovery.

Provides endpoints to list available scenarios with their knobs files and
read knobs file contents. Simulation launches happen via the CLI.
"""

import logging

import orjson
from fastapi import APIRouter, HTTPException

from glossogen.scenario_loader import find_scenario_class, iter_scenario_classes
from glossogen.server.scenarios.models import (
    KnobsContentResponse,
    ModelInfo,
    ScenarioInfo,
    ScenariosResponse,
)
from glossogen.token_pricing import list_models, list_providers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/g/{group_slug}")


@router.get("/scenarios", response_model=ScenariosResponse)
async def list_scenarios() -> ScenariosResponse:
    """List all available scenarios with their knobs files and supported providers."""
    scenarios: list[ScenarioInfo] = []
    for name, scenario_cls in iter_scenario_classes():
        scenarios.append(
            ScenarioInfo(
                scenario_name=name,
                knobs_files=scenario_cls.knobs_preset_names(),
                available_metrics=scenario_cls.get_available_metric_names(),
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
    """Return the contents of one of a scenario's knobs presets."""
    scenario_cls = find_scenario_class(name=scenario_name)
    if scenario_cls is None:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_name}")

    try:
        knobs = scenario_cls.load_knobs_preset(preset_name=knobs_name)
    except orjson.JSONDecodeError as exc:
        # Caught before ValueError, which it subclasses. Reporting a preset that
        # exists but will not parse as "not found" sends the reader looking for a
        # missing file instead of at the syntax error in front of them.
        logger.exception("Knobs preset %s/%s is not valid JSON", scenario_name, knobs_name)
        raise HTTPException(
            status_code=422,
            detail=f"Knobs file is not valid JSON: {knobs_name}",
        ) from exc
    except ValueError as exc:
        logger.exception("Knobs preset lookup failed for %s/%s", scenario_name, knobs_name)
        raise HTTPException(status_code=404, detail=f"Knobs file not found: {knobs_name}") from exc
    return KnobsContentResponse(knobs=knobs)
