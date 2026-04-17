"""Shared base models for scenario knobs."""

from pydantic import BaseModel, ConfigDict


class AgentModelOverride(BaseModel):
    """Per-agent model/provider override configured in scenario knobs."""

    model_config = ConfigDict(extra="forbid")

    model: str
    provider: str | None = None


class BaseKnobs(BaseModel):
    """Base knobs shared by all scenarios.

    ``postmortem_duration_seconds`` defaults to 120 and is only meaningful
    when a scenario enables postmortem. Scenarios that do not use postmortem
    can ignore it entirely.
    """

    model_config = ConfigDict(extra="ignore")

    max_round_duration_seconds: float
    model_overrides: dict[str, AgentModelOverride]
    postmortem_duration_seconds: float = 120.0
