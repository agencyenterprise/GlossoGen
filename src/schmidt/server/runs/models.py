"""Pydantic response models for simulation run endpoints and SSE event schemas."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Discriminator

from schmidt.evaluation.evaluation_report import Verdict
from schmidt.models.event import RunStatus
from schmidt.server.response_models import LaunchStatus


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


class SwapPoint(BaseModel):
    """Anchor for the moment agents were swapped between teams.

    ``target_message_id`` is the first ``MessageSent`` on a link channel
    after the swap fired, used by the frontend to scroll the timeline
    to that exact point. ``swapped_observer_display_names`` are the
    two observers who exchanged teams, in stable order.
    """

    round_number: int
    target_message_id: str
    swapped_observer_display_names: list[str]


class InternAnchor(BaseModel):
    """Anchor for a timeline event in the Veyru intern-mode lifecycle.

    Used for both the intern-join moment and the intern-takeover moment.
    ``target_message_id`` is the first ``MessageSent`` on the link channel
    after the anchor fired, so the frontend can scroll to that point.
    """

    round_number: int
    target_message_id: str


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
    models: list[str]
    provider: str
    agent_models: list[AgentModelSummary]
    labels: list[str]
    has_note: bool
    current_round: int


class RunListResponse(BaseModel):
    """Response model for the list-all-runs endpoint."""

    runs: list[RunSummary]


class AgentDetail(BaseModel):
    """Full agent information for the run detail endpoint."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    model: str
    provider: str
    system_prompt: str


class ChannelMessage(BaseModel):
    """A message sent by an agent to a channel."""

    message_id: str
    channel_id: str
    sender_agent_id: str
    text: str
    timestamp: datetime
    round_number: int
    token_count: int


class VeyruStabilizeMetadata(BaseModel):
    """Judge context captured for a single ``stabilize_veyru`` call.

    Attached to the corresponding ``ToolUseEntry`` so the frontend can show
    the expected procedure and the LLM judge's verdict alongside the raw
    tool call. Present only on ``stabilize_veyru`` entries.
    """

    expected_actions: str
    judge_match: bool
    judge_explanation: str


class VeyruStellarReadingDTO(BaseModel):
    """Per-round stellar parameters shaping the Veyru procedure mapping."""

    offset: int
    hold_duration: int
    starting_face: str
    intensity_level: str


class VeyruCaseStageDTO(BaseModel):
    """One stage of a Veyru case with symptoms and the expected procedure."""

    motif_name: str
    observable_symptoms: str
    treatment_motif_name: str
    judge_expected_actions: str


class VeyruCaseSummary(BaseModel):
    """Per-round Veyru case metadata used by the round timeline modal.

    One entry per round when the scenario is Veyru. Mirrors the
    ``VeyruCaseStarted`` event emitted at each round start.
    """

    round_number: int
    case_number: int
    failure_name: str
    time_budget_seconds: int
    stages: list[VeyruCaseStageDTO]
    stellar_reading: VeyruStellarReadingDTO


class RoundEnding(BaseModel):
    """Reason a round's main phase ended.

    One entry per round end, across all scenarios. ``trigger`` matches the
    ``RoundEnded.trigger`` field (e.g. ``veyru_stabilized``,
    ``all_agents_idle``, ``veyru_collapsed``, ``round_timeout``).
    """

    round_number: int
    trigger: str
    timestamp: datetime


class ToolUseEntry(BaseModel):
    """A scenario-specific tool invocation with its result.

    Each entry represents one tool call made by an agent. The ``result``
    field is filled once the tool execution completes. ``timestamp``
    anchors to ``tool_call_invoked``; ``result_timestamp`` anchors to
    ``tool_result_received`` so the UI can render call and result at
    their true chronological positions.
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
    stabilize_metadata: VeyruStabilizeMetadata | None = None


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


class EvalMetricResponse(BaseModel):
    """Result of a single evaluator for the run detail endpoint."""

    evaluator_name: str
    verdict: Verdict
    score: float
    evidence: list[str]
    per_agent: dict[str, Verdict]


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

    metrics: list[EvalMetricResponse]
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
    messages: list[ChannelMessage]
    reasoning: list[ReasoningEntry]
    tool_use: list[ToolUseEntry]
    run_cycle_failures: list[AgentRunCycleFailedEntry]
    evaluation: EvalReportResponse | None
    evaluation_in_progress: bool
    has_eval_log_file: bool
    fork_source: ForkSource | None
    replace_agent_source: ReplaceAgentSource | None
    swap_point: SwapPoint | None
    intern_join: InternAnchor | None
    intern_takeover: InternAnchor | None
    labels: list[str]
    note: str | None
    veyru_cases: list[VeyruCaseSummary]
    round_endings: list[RoundEnding]


class DebugLogsResponse(BaseModel):
    """Response containing debug log entries for a simulation run."""

    entries: list[DebugLogEntry]


class StartEvaluationRequest(BaseModel):
    """Request body for starting an evaluation on a completed run."""

    model: str
    provider: str
    evaluators: list[str]


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


class MessageEdit(BaseModel):
    """A single message text edit for a fork request."""

    message_id: str
    new_text: str


class ForkRequest(BaseModel):
    """Request body for creating a forked simulation run."""

    model_config = ConfigDict(extra="forbid")

    target_message_id: str
    message_edits: list[MessageEdit]
    model: str
    provider: str
    knobs: dict[str, Any] | None


class ForkResponse(BaseModel):
    """Response returned after a fork is created."""

    fork_run_id: str
    fork_run_dir: str


# ---------------------------------------------------------------------------
# Replace-agent request/response models
# ---------------------------------------------------------------------------


class ReplaceAgentRequest(BaseModel):
    """Request body for replacing one agent in a finished run at the start of a round.

    ``channels_with_visible_history`` lists channel IDs whose prior history
    remains visible to the replaced agent on resume; every other channel
    they're a member of has its history wiped.

    ``rounds_after_swap`` controls how many rounds the resumed simulation
    plays following the replacement: ``round_count`` is set to
    ``round_start + rounds_after_swap``. When ``None``, defaults to
    ``source_round_count - round_start`` (the remaining rounds in the
    original run after the replacement boundary).
    """

    model_config = ConfigDict(extra="forbid")

    round_start: int
    rounds_after_swap: int | None
    replaced_agent_id: str
    model: str
    provider: str
    knobs: dict[str, Any] | None
    channels_with_visible_history: list[str]


class ReplaceAgentResponse(BaseModel):
    """Response returned after a replace-agent run is launched."""

    new_run_id: str
    new_run_dir: str


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
# Prod upload models
# ---------------------------------------------------------------------------


class ProdUploadStatusResponse(BaseModel):
    """Whether prod upload is configured on this server."""

    configured: bool
    prod_url: str | None


class ProdUploadOutcome(str, Enum):
    """Outcome of a single-run prod upload."""

    UPLOADED = "uploaded"
    ALREADY_PRESENT = "already_present"
    OVERRIDDEN = "overridden"


class ProdUploadResponse(BaseModel):
    """Result of uploading one run to the configured prod server."""

    run_id: str
    outcome: ProdUploadOutcome


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


class SSEVeyruStabilizationJudged(BaseModel):
    """SSE event carrying the veyru stabilization judge's verdict for a stabilize_veyru call."""

    event_type: Literal["veyru_stabilization_judged"]
    event_id: str
    timestamp: datetime
    agent_id: str
    round_number: int
    expected_actions: str
    judge_match: bool
    judge_explanation: str


SSEEvent = Annotated[
    Union[
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
        SSEVeyruStabilizationJudged,
    ],
    Discriminator("event_type"),
]
