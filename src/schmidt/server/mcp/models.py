"""Pydantic response models for MCP tool outputs."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class McpScenario(BaseModel):
    """A single scenario entry for the list_scenarios response."""

    name: str
    knobs_files: list[str]
    metrics: list[str]


class McpModel(BaseModel):
    """A supported model entry."""

    model_prefix: str
    provider: str


class McpListScenariosResult(BaseModel):
    """Response for list_scenarios."""

    scenarios: list[McpScenario]
    models: list[McpModel]
    providers: list[str]


class McpAgentModel(BaseModel):
    """Per-agent model info for run summaries."""

    agent_id: str
    role_name: str
    model: str
    provider: str


class McpForkSource(BaseModel):
    """Fork provenance info."""

    source_run_id: str
    target_message_id: str
    forked_at: datetime


class McpRunEntry(BaseModel):
    """A single run entry for the list_runs response."""

    run_id: str
    scenario_name: str
    status: str
    timestamp: datetime
    total_messages: int
    total_cost_usd: float
    duration_seconds: float
    provider: str
    models: list[str]
    is_forked: bool
    has_evaluation: bool
    agent_models: list[McpAgentModel]
    fork_source: McpForkSource | None


class McpListRunsResult(BaseModel):
    """Response for list_runs."""

    runs: list[McpRunEntry]
    total: int
    offset: int
    limit: int


class McpHeadlineMeasurement(BaseModel):
    """Compact eval measurement surfaced inline on a derived run entry."""

    metric_name: str
    score: float
    score_unit: str
    summary: str


class McpDerivedRun(BaseModel):
    """One child run derived from a parent run.

    A child is any run whose timeline parent is the queried run: created via
    ``replace-agent`` (``derivation_type == "replace_agent"``),
    ``resume-at-round`` (``"resume_at_round"``), or ``cross-run-replace-agent``
    with the queried run as source A (``"cross_run_replace_agent"``).
    """

    run_id: str
    derivation_type: Literal["replace_agent", "resume_at_round", "cross_run_replace_agent"]
    round_start: int
    rounds_after_swap: int | None
    rounds_after_resume: int | None
    replaced_agent_id: str | None
    replacement_model: str | None
    replacement_provider: str | None
    imported_model: str | None
    imported_provider: str | None
    source_b_run_id: str | None
    source_b_round_end: int | None
    created_at: datetime
    status: str
    current_round: int
    target_round_count: int | None
    total_messages: int
    total_cost_usd: float
    labels: list[str]
    has_evaluation: bool
    headline_measurements: list[McpHeadlineMeasurement]


class McpListDerivedRunsResult(BaseModel):
    """Response for list_derived_runs."""

    parent_run_id: str
    derived_runs: list[McpDerivedRun]
    total: int


class McpRoundObservation(BaseModel):
    """Per-round observation for an evaluation measurement."""

    round_number: int
    value: float
    note: str


class McpAgentObservation(BaseModel):
    """Per-agent observation for an evaluation measurement."""

    agent_id: str
    value: float
    note: str


class McpMeasurement(BaseModel):
    """A single evaluation measurement."""

    metric_name: str
    score: float
    score_unit: str
    summary: str
    per_round: list[McpRoundObservation]
    per_agent: list[McpAgentObservation]


class McpRunMetadata(BaseModel):
    """Response for get_run_metadata."""

    run_id: str
    scenario_name: str
    status: str
    timestamp: datetime
    total_messages: int
    total_cost_usd: float
    duration_seconds: float
    provider: str
    models: list[str]
    is_forked: bool
    scenario_config: dict[str, Any]
    agent_models: list[McpAgentModel]
    fork_source: McpForkSource | None
    evaluation: list[McpMeasurement] | None


class McpMessage(BaseModel):
    """A channel message in the get_run response."""

    message_id: str
    channel_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime
    round_number: int


class McpReasoning(BaseModel):
    """An LLM reasoning entry."""

    message_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime
    round_number: int


class McpToolCall(BaseModel):
    """A tool invocation entry."""

    message_id: str
    sender_agent_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: str | None
    timestamp: datetime
    round_number: int


class McpAgent(BaseModel):
    """Agent info with optional system prompt."""

    agent_id: str
    role_name: str
    model: str
    provider: str
    tool_names: list[str]
    channel_ids: list[str]
    system_prompt: str | None


class McpDebugLog(BaseModel):
    """A debug log entry."""

    timestamp: str
    logger_name: str
    level: str
    message: str


class McpGetRunResult(BaseModel):
    """Response for get_run."""

    run_id: str
    scenario_name: str
    messages: list[McpMessage]
    total_messages: int
    message_offset: int
    message_limit: int
    agents: list[McpAgent] | None
    reasoning: list[McpReasoning] | None
    tool_use: list[McpToolCall] | None
    debug_logs: list[McpDebugLog] | None


class McpGetKnobsSchemaResult(BaseModel):
    """Response for get_knobs_schema."""

    scenario_name: str
    knobs_schema: dict[str, Any]
    knobs_files: list[str]


class McpGetKnobsPresetResult(BaseModel):
    """Response for get_knobs_preset."""

    scenario_name: str
    knobs_file: str
    knobs: dict[str, Any]


class McpStartRunResult(BaseModel):
    """Response for start_run."""

    status: str
    scenario_name: str
    model: str
    provider: str


class McpExportArtifactsResult(BaseModel):
    """Response for export_run_artifacts."""

    run_id: str
    scenario_name: str
    download_url: str
    filename: str
