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

    ``replace_agent_default_channel_visibility`` maps channel IDs to a
    boolean that determines whether the replace-agent flow makes that
    channel's prior history visible to the replaced agent by default.
    Channel IDs not in the map default to ``True`` (visible). The
    simulation itself does not read this field at runtime; only the
    replace-agent CLI/HTTP/FE flows consult it to populate defaults.
    """

    model_config = ConfigDict(extra="ignore")

    max_round_duration_seconds: float
    model_overrides: dict[str, AgentModelOverride]
    postmortem_duration_seconds: float = 120.0
    replace_agent_default_channel_visibility: dict[str, bool] = {}
