"""Pydantic response models for scenario discovery."""

from typing import Any

from pydantic import BaseModel


class ScenarioInfo(BaseModel):
    """Metadata about a single scenario, including its available knobs files."""

    scenario_name: str
    knobs_files: list[str]
    available_metrics: list[str]


class ModelInfo(BaseModel):
    """A supported model prefix and its provider."""

    model_prefix: str
    provider: str


class ScenariosResponse(BaseModel):
    """Response listing all available scenarios, models, and providers."""

    scenarios: list[ScenarioInfo]
    models: list[ModelInfo]
    providers: list[str]


class KnobsContentResponse(BaseModel):
    """Response containing the parsed contents of a knobs JSON file."""

    knobs: dict[str, Any]
