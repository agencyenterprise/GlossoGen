"""Pydantic request/response models for scenario discovery and simulation launch."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from schmidt.server.response_models import LaunchStatus


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


class AgentRoleInfo(BaseModel):
    """Lightweight agent identity for the agent discovery endpoint.

    ``channels`` lists the channel IDs the agent is a member of given
    the supplied knobs. Used by the FE phase-builder to render per-agent
    channel-visibility controls when configuring scheduled swaps.
    """

    agent_id: str
    role_name: str
    channels: list[str]


class AgentRolesRequest(BaseModel):
    """Request body for discovering agents in a scenario."""

    knobs: dict[str, Any] | None


class AgentRolesResponse(BaseModel):
    """Response listing agents that would participate in a scenario."""

    agents: list[AgentRoleInfo]


class StartRunRequest(BaseModel):
    """Request body for starting a new simulation run."""

    model_config = ConfigDict(extra="forbid")

    scenario_name: str
    model: str
    provider: str
    knobs: dict[str, Any] | None


class StartRunResponse(BaseModel):
    """Response after successfully launching a new simulation."""

    status: LaunchStatus
