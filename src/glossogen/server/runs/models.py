"""Pydantic response models for simulation run endpoints and SSE event schemas."""

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Discriminator

from glossogen.models.event import RunStatus
from glossogen.server.response_models import LaunchStatus
from glossogen.server.runs.run_detail_types import AgentDetail, ChannelMessage
from glossogen.server.runs.scenario_extension import SCENARIO_RUN_EXTENSIONS, ScenarioRunExtrasBase

_SCENARIO_EXTRAS_TYPES: tuple[type[ScenarioRunExtrasBase], ...] = tuple(
    ext.extras_model_cls for ext in SCENARIO_RUN_EXTENSIONS.values()
)

# ``ScenarioRunExtras`` is a runtime-built discriminated union over every
# ``ScenarioRunExtrasBase`` subclass advertised by a scenario's
# ``run_detail_extension`` module. ``Union`` accepts a tuple at runtime;
# the ``Any`` cast hides this from the static type checker since the
# tuple is only known at runtime. When no scenario advertises extras the
# union falls back to the base class so the OpenAPI schema stays valid.
if _SCENARIO_EXTRAS_TYPES:
    _scenario_extras_union: Any = Union[_SCENARIO_EXTRAS_TYPES]
else:
    _scenario_extras_union = ScenarioRunExtrasBase
ScenarioRunExtras = Annotated[_scenario_extras_union, Discriminator("scenario_name")]


class ForkSource(BaseModel):
    """Provenance information for a forked simulation run."""

    source_run_id: str
    target_message_id: str
    forked_at: datetime


class ReplaceAgentSource(BaseModel):
    """Provenance for a run created via the replace-agent endpoint.

    The replacement boundary is the start of round ``round_start``.
    ``target_event_id`` is the resolved anchor inside the source
    run's git history (the ``RoundAdvanced`` event for ``round_start``),
    kept for traceability.
    """

    source_run_id: str
    round_start: int
    target_event_id: str
    replaced_agent_id: str
    replacement_model: str
    replacement_provider: str
    replaced_at: datetime


class ResumeAtRoundSource(BaseModel):
    """Provenance for a run created via the resume-at-round endpoint.

    The resume boundary is the start of round ``round_start``. No agent
    is replaced — every agent keeps its full reconstructed history; the
    resumed simulation differs from the source only via merged knob
    overrides (e.g. ``postmortem_enabled``, ``scheduled_events``,
    ``round_count``).
    """

    source_run_id: str
    round_start: int
    rounds_after_resume: int
    target_event_id: str
    resumed_at: datetime


class CrossRunReplaceAgentSource(BaseModel):
    """Provenance for a run created via the cross-run replace-agent endpoint.

    ``source_a_run_id`` is the target run whose timeline was modified.
    ``source_b_run_id`` is the run the imported agent came from.
    ``source_b_round_end`` is the last Sim B round whose events fed
    into the imported agent's history.
    """

    source_a_run_id: str
    source_b_run_id: str
    round_start: int
    source_b_round_end: int
    target_event_id: str
    replaced_agent_id: str
    imported_model: str
    imported_provider: str
    replaced_at: datetime


class HeadlineMeasurement(BaseModel):
    """Compact eval measurement surfaced inline on a derived run reference."""

    metric_name: str
    score: float
    score_unit: str
    summary: str


class DerivedRunReference(BaseModel):
    """One child run derived from the parent currently being viewed.

    A child is any run whose timeline parent is this run: created via
    ``replace-agent`` (``derivation_type == "replace_agent"``),
    ``resume-at-round`` (``"resume_at_round"``), or
    ``cross-run-replace-agent`` with this run as source A
    (``"cross_run_replace_agent"``). Source-B-only usage is not represented.
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
    status: RunStatus
    current_round: int
    target_round_count: int | None
    total_messages: int
    total_cost_usd: float
    labels: list[str]
    has_evaluation: bool
    headline_measurements: list[HeadlineMeasurement]


class AgentModelSummary(BaseModel):
    """Per-agent model and provider info for run summary display."""

    agent_id: str
    role_name: str
    model: str
    provider: str


class RunSummary(BaseModel):
    """Summary of a single simulation run for the runs list endpoint."""

    run_id: str
    scenario_name: str
    scenario_description: str
    scenario_config: dict[str, Any]
    timestamp: datetime
    total_messages: int
    total_cost_usd: float
    duration_seconds: float
    status: RunStatus
    has_evaluation: bool
    evaluation_in_progress: bool
    run_dir: str
    fork_source: ForkSource | None
    replace_agent_source: ReplaceAgentSource | None
    cross_run_replace_agent_source: CrossRunReplaceAgentSource | None
    resume_at_round_source: ResumeAtRoundSource | None
    models: list[str]
    provider: str
    agent_models: list[AgentModelSummary]
    labels: list[str]
    has_note: bool
    current_round: int
    evaluation_content_hash: str | None


class RunListResponse(BaseModel):
    """Response model for the paginated runs endpoint.

    ``runs`` is one page (newest-first); ``total`` is the number of runs
    matching the request's filters before paging, for the load-more UI.
    """

    runs: list[RunSummary]
    total: int


class BranchSourceSummary(BaseModel):
    """One source run that has been used as a derivation parent.

    ``source_run`` is the parent's full summary; ``derived_count`` is how many
    runs (replace-agent, resume-at-round, cross-run-replace-agent source A)
    branch from it.
    """

    source_run: RunSummary
    derived_count: int


class BranchListResponse(BaseModel):
    """Response model for the branches endpoint.

    Every entry is a run that has at least one derived child, newest parent
    first. Enriches only the parent runs (there are far fewer parents than
    derivations), so the branches view never fetches the whole run set.
    """

    sources: list[BranchSourceSummary]


class AgentSwapEventDTO(BaseModel):
    """One in-run agent swap, surfaced for per-instance tab rendering on the FE.

    Each ``AgentSwappedMidRun`` event in the run's JSONL becomes one DTO.
    The FE groups consecutive events by ``agent_id`` to derive an ordered
    list of agent instances (generations) and split message visibility
    by round range.
    """

    agent_id: str
    round_number: int
    timestamp: datetime
    new_model: str
    new_provider: str
    system_prompt: str


class ContextCompactionEventDTO(BaseModel):
    """One provider-native history compaction, surfaced for the run viewer.

    Each ``ContextCompacted`` event in the run's JSONL becomes one DTO. The FE
    renders a per-agent marker at ``round_number``. ``summary_text`` carries the
    provider's readable summary when available (Anthropic); it is empty when the
    provider stores the summary encrypted server-side (OpenAI), in which case
    ``summary_char_count`` is 0.
    """

    agent_id: str
    round_number: int
    timestamp: datetime
    provider_name: str
    summary_char_count: int
    summary_text: str


class RoundEnding(BaseModel):
    """Reason a round's main phase ended.

    One entry per round end, across all scenarios. ``trigger`` matches the
    ``RoundEnded.trigger`` field (e.g. ``veyru_stabilized``,
    ``all_agents_idle``, ``veyru_collapsed``, ``round_timeout``).
    """

    round_number: int
    trigger: str
    timestamp: datetime


class RoundResult(BaseModel):
    """Structured per-round outcome emitted by the scenario.

    Mirrors the ``RoundResultRecorded`` event. Single-team scenarios emit
    one entry per round with ``team_id=None``; multi-team scenarios emit one
    entry per team.
    """

    round_number: int
    success: bool
    team_id: str | None
    reason: str


class RoundInjection(BaseModel):
    """A scenario injection delivered to an agent at a round boundary.

    Mirrors the ``InjectionDelivered`` event. One entry per delivery; the
    same injection text is typically delivered to every agent on a channel.
    """

    round_number: int
    agent_id: str
    text: str
    timestamp: datetime


class ToolUseEntry(BaseModel):
    """A scenario-specific tool invocation with its result.

    Each entry represents one tool call made by an agent. The ``result``
    field is filled once the tool execution completes. ``timestamp``
    anchors to ``tool_call_invoked``; ``result_timestamp`` anchors to
    ``tool_result_received`` so the UI can render call and result at
    their true chronological positions. ``round_number`` is the round
    the call was issued in; ``result_round_number`` is the round the
    result was received in. They differ for tool calls that hang across
    a round boundary (e.g. ``read_notifications`` blocking until the
    next round's injection arrives).
    """

    message_id: str
    sender_agent_id: str
    tool_name: str
    call_id: str
    arguments: dict[str, Any]
    result: str | None
    timestamp: datetime
    result_timestamp: datetime | None
    round_number: int
    result_round_number: int | None


class ReasoningEntry(BaseModel):
    """An LLM reasoning/thinking entry from an agent's turn.

    ``channel_ids`` links this reasoning to the channels of the surrounding
    send_message calls from the same agent, so the frontend can show only
    reasoning relevant to the selected channel.
    """

    message_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime
    round_number: int
    channel_ids: list[str]


class DebugLogEntry(BaseModel):
    """A single debug log entry from the simulation run."""

    timestamp: str
    logger_name: str
    level: str
    message: str


class AgentRunCycleFailedEntry(BaseModel):
    """A single agent-run-cycle failure extracted from the event log.

    One entry per ``AgentRunCycleFailed`` event. ``error_type`` is the
    exception class name (e.g. ``"ContentFilterError"``).
    """

    message_id: str
    agent_id: str
    timestamp: datetime
    round_number: int
    cycle: int
    error_type: str
    message: str


class RoundObservationResponse(BaseModel):
    """Per-round observation for an evaluation measurement."""

    round_number: int
    value: float
    note: str


class AgentObservationResponse(BaseModel):
    """Per-agent observation for an evaluation measurement."""

    agent_id: str
    value: float
    note: str


class MeasurementResponse(BaseModel):
    """Numeric measurement produced by a single metric for the run detail endpoint."""

    metric_name: str
    score: float
    score_unit: str
    summary: str
    per_round: list[RoundObservationResponse]
    per_agent: list[AgentObservationResponse]


class EvalCostResponse(BaseModel):
    """Evaluation cost summary for the run detail endpoint."""

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    estimated_cost_usd: float
    model: str
    provider_name: str


class EvalReportResponse(BaseModel):
    """Evaluation report for the run detail endpoint."""

    measurements: list[MeasurementResponse]
    evaluation_cost: EvalCostResponse | None


class RunDetailResponse(BaseModel):
    """Full detail of a simulation run including agents, messages, and evaluation."""

    run_id: str
    scenario_name: str
    scenario_description: str
    scenario_config: dict[str, Any]
    timestamp: datetime
    total_messages: int
    total_cost_usd: float
    duration_seconds: float
    status: RunStatus
    channel_ids: list[str]
    provider: str
    agents: list[AgentDetail]
    agent_swap_events: list[AgentSwapEventDTO]
    context_compaction_events: list[ContextCompactionEventDTO]
    messages: list[ChannelMessage]
    reasoning: list[ReasoningEntry]
    tool_use: list[ToolUseEntry]
    run_cycle_failures: list[AgentRunCycleFailedEntry]
    evaluation: EvalReportResponse | None
    evaluation_in_progress: bool
    has_eval_log_file: bool
    fork_source: ForkSource | None
    replace_agent_source: ReplaceAgentSource | None
    cross_run_replace_agent_source: CrossRunReplaceAgentSource | None
    resume_at_round_source: ResumeAtRoundSource | None
    children: list[DerivedRunReference]
    labels: list[str]
    note: str | None
    round_endings: list[RoundEnding]
    round_results: list[RoundResult]
    round_injections: list[RoundInjection]
    scenario_extras: ScenarioRunExtras | None


class DebugLogsResponse(BaseModel):
    """Response containing debug log entries for a simulation run."""

    entries: list[DebugLogEntry]


class StartEvaluationRequest(BaseModel):
    """Request body for starting an evaluation on a completed run."""

    model: str
    provider: str
    metrics: list[str]


class StartEvaluationResponse(BaseModel):
    """Response after successfully launching an evaluation subprocess."""

    status: LaunchStatus


class EvalLogLine(BaseModel):
    """A single line from the evaluation stdout log."""

    line_number: int
    text: str


class EvalLogsResponse(BaseModel):
    """Response containing evaluation subprocess stdout/stderr output."""

    lines: list[EvalLogLine]


# ---------------------------------------------------------------------------
# Fork request/response models
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Labels and notes request/response models
# ---------------------------------------------------------------------------


class UpdateLabelsRequest(BaseModel):
    """Request body for setting labels on a run."""

    labels: list[str]


class UpdateLabelsResponse(BaseModel):
    """Response after updating labels on a run."""

    labels: list[str]


class UpdateNoteRequest(BaseModel):
    """Request body for setting or updating a note on a run."""

    content: str


class UpdateNoteResponse(BaseModel):
    """Response after updating a note on a run."""

    content: str


class UpdateEvaluationResponse(BaseModel):
    """Response after replacing a run's evaluation report on disk."""

    run_id: str
    measurement_count: int


class NoteResponse(BaseModel):
    """Lightweight response for fetching a run's note content."""

    content: str | None


class AllLabelsResponse(BaseModel):
    """Response containing all unique labels across all runs."""

    labels: list[str]


# ---------------------------------------------------------------------------
# Bundle export/import models
# ---------------------------------------------------------------------------


class BundleManifest(BaseModel):
    """Metadata embedded in an exported run bundle tar.gz."""

    run_id: str
    scenario_name: str
    exported_at: datetime
    original_timestamp: int


class ImportBundleResponse(BaseModel):
    """Response after successfully importing a run bundle."""

    run_id: str
    scenario_name: str
    run_dir: str


# ---------------------------------------------------------------------------
# SSE event schemas
# ---------------------------------------------------------------------------


class SSESimulationMessagePayload(BaseModel):
    """Nested message payload inside an SSE message_sent event."""

    message_id: str
    channel_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime


class SSESimulationStarted(BaseModel):
    """SSE event emitted once when a simulation begins."""

    event_type: Literal["simulation_started"]
    event_id: str
    run_id: str
    timestamp: datetime
    scenario_name: str
    scenario_description: str
    channel_ids: list[str]
    scenario_config: dict[str, Any]


class SSEAgentRegistered(BaseModel):
    """SSE event emitted when an agent joins the simulation."""

    event_type: Literal["agent_registered"]
    event_id: str
    timestamp: datetime
    agent_id: str
    role_name: str
    system_prompt: str
    channel_ids: list[str]
    tool_names: list[str]
    model: str
    provider: str


class SSEAgentConnected(BaseModel):
    """SSE event emitted when an agent connects to the MCP server."""

    event_type: Literal["agent_connected"]
    event_id: str
    timestamp: datetime
    agent_id: str


class SSEMessageSent(BaseModel):
    """SSE event emitted when an agent sends a message to a channel."""

    event_type: Literal["message_sent"]
    event_id: str
    timestamp: datetime
    message: SSESimulationMessagePayload
    round_number: int
    token_count: int


class SSELLMResponseReceived(BaseModel):
    """SSE event emitted when the LLM returns a response (reasoning text)."""

    event_type: Literal["llm_response_received"]
    event_id: str
    timestamp: datetime
    agent_id: str
    text: str | None
    round_number: int


class SSEToolCallInvoked(BaseModel):
    """SSE event emitted when an agent invokes a tool, before execution."""

    event_type: Literal["tool_call_invoked"]
    event_id: str
    timestamp: datetime
    agent_id: str
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    round_number: int


class SSEToolResultReceived(BaseModel):
    """SSE event emitted when a tool call completes and returns a result."""

    event_type: Literal["tool_result_received"]
    event_id: str
    timestamp: datetime
    agent_id: str
    tool_name: str
    call_id: str
    arguments: dict[str, Any]
    result: str
    round_number: int


class SSERoundAdvanced(BaseModel):
    """SSE event emitted when the game clock advances to a new round."""

    event_type: Literal["round_advanced"]
    event_id: str
    timestamp: datetime
    round_number: int
    trigger: str


class SSEInjectionDelivered(BaseModel):
    """SSE event emitted when a scenario injection is pushed to an agent."""

    event_type: Literal["injection_delivered"]
    event_id: str
    timestamp: datetime
    agent_id: str
    round_number: int
    injection_text: str


class SSESimulationEnded(BaseModel):
    """SSE event emitted once when the simulation finishes."""

    event_type: Literal["simulation_ended"]
    event_id: str
    timestamp: datetime
    reason: RunStatus
    total_messages: int
    total_cost_usd: float
    duration_seconds: float


class SSEAgentCostUpdated(BaseModel):
    """SSE event carrying an agent's cumulative cost after each run cycle.

    Transient — not persisted to JSONL. The final total arrives in
    ``SSESimulationEnded``.
    """

    event_type: Literal["agent_cost_updated"]
    agent_id: str
    cumulative_cost_usd: float


class SSEDebugLog(BaseModel):
    """SSE event for a real-time debug log entry from the simulation process."""

    event_type: Literal["debug_log"]
    timestamp: str
    logger_name: str
    level: str
    message: str


class SSEAgentRunCycleFailed(BaseModel):
    """SSE event emitted when agent.run() raised an exception in the runner's retry loop."""

    event_type: Literal["agent_run_cycle_failed"]
    event_id: str
    timestamp: datetime
    agent_id: str
    round_number: int
    cycle: int
    error_type: str
    message: str


_CORE_SSE_TYPES: tuple[type[BaseModel], ...] = (
    SSESimulationStarted,
    SSEAgentRegistered,
    SSEAgentConnected,
    SSEMessageSent,
    SSELLMResponseReceived,
    SSEToolCallInvoked,
    SSEToolResultReceived,
    SSERoundAdvanced,
    SSEInjectionDelivered,
    SSESimulationEnded,
    SSEAgentCostUpdated,
    SSEDebugLog,
    SSEAgentRunCycleFailed,
)

_SCENARIO_SSE_TYPES: tuple[type[BaseModel], ...] = tuple(
    cls for ext in SCENARIO_RUN_EXTENSIONS.values() for cls in ext.sse_event_classes
)

_sse_event_union: Any = Union[(*_CORE_SSE_TYPES, *_SCENARIO_SSE_TYPES)]
SSEEvent = Annotated[_sse_event_union, Discriminator("event_type")]
