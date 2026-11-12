"""Pydantic request and response models for the run endpoints, and the SSE event schemas.

The run record these responses carry, :class:`RunSummary` and its parts, lives in
:mod:`glossogen.run_storage.run_summary_models`.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Discriminator, JsonValue, SerializeAsAny

from glossogen.models.agent_model_settings import AgentModelSettings
from glossogen.models.event import RunStatus
from glossogen.models.thinking_part_record import ThinkingPartRecord
from glossogen.run_storage.run_summary_models import (
    CrossRunReplaceAgentSource,
    EvaluationScore,
    ForkAtRoundSource,
    ForkSource,
    ReplaceAgentSource,
    RunSummary,
)
from glossogen.scenario_contract.run_detail_extension import ScenarioRunExtrasBase
from glossogen.scenario_contract.run_detail_types import AgentDetail, ChannelMessage
from glossogen.server.response_models import LaunchStatus


class DerivedRunReference(BaseModel):
    """One child run derived from the parent currently being viewed.

    A child is any run whose timeline parent is this run: created via
    ``replace-agent`` (``derivation_type == "replace_agent"``),
    ``fork-at-round`` (``"fork_at_round"``), or
    ``cross-run-replace-agent`` with this run as source A
    (``"cross_run_replace_agent"``). Source-B-only usage is not represented.
    ``after_round`` is the fork boundary and ``rounds_after`` the number of
    new rounds the child plays past it.
    """

    run_id: str
    derivation_type: Literal["replace_agent", "fork_at_round", "cross_run_replace_agent"]
    after_round: int
    rounds_after: int
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
    evaluation_scores: list[EvaluationScore] | None
    headline_measurements: list[EvaluationScore]


class RunListResponse(BaseModel):
    """Response model for the paginated runs endpoint.

    ``runs`` is one page (newest-first); ``total`` is the number of runs
    matching the request's filters before paging, for the load-more UI.
    ``next_cursor`` is the opaque keyset cursor to pass back for the following
    page, or ``None`` when the returned page is the last one.
    """

    runs: list[RunSummary]
    total: int
    next_cursor: str | None


class BranchSourceSummary(BaseModel):
    """One source run that has been used as a derivation parent.

    ``source_run`` is the parent's full summary; ``derived_count`` is how many
    runs (replace-agent, fork-at-round, cross-run-replace-agent source A)
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
    by round range. ``model_settings`` are what the swapped-in agent was sent.
    """

    agent_id: str
    round_number: int
    timestamp: datetime
    new_model: str
    new_provider: str
    model_settings: AgentModelSettings
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


class ReasoningKind(str, Enum):
    """What a reasoning entry holds.

    ``text`` is what the model wrote in the response. ``thinking`` is the
    reasoning the provider exposed beside it: Anthropic's thinking blocks, or
    the summary OpenAI returns for a reasoning model that writes no text.
    """

    TEXT = "text"
    THINKING = "thinking"


class ReasoningEntry(BaseModel):
    """An LLM reasoning/thinking entry from an agent's turn.

    ``channel_ids`` links this reasoning to the channels of the surrounding
    send_message calls from the same agent, so the frontend can show only
    reasoning relevant to the selected channel.
    """

    message_id: str
    sender_agent_id: str
    kind: ReasoningKind
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


class UnrecognizedEventEntry(BaseModel):
    """A logged event that neither the platform nor the run's loaded scenario declares.

    One entry per ``UnrecognizedEvent`` the run's log read back as. ``payload`` is
    the whole line as logged.
    """

    event_id: str
    event_type: str
    round_number: int
    timestamp: datetime
    payload: dict[str, JsonValue]


class ClosingExchangeStatus(str, Enum):
    """How an agent's closing exchange ended: with an answer, or with a failure."""

    ANSWERED = "answered"
    FAILED = "failed"


class ClosingExchangeEntry(BaseModel):
    """One agent's closing exchange: the prompt sent once the run completed, and its outcome.

    One entry per ``ClosingPromptAnswered`` or ``ClosingPromptFailed`` event.
    ``answer`` is set when ``status`` is ``answered``, and ``failure`` holds the
    error type and message when it is ``failed``.
    """

    message_id: str
    agent_id: str
    model: str
    prompt: str
    status: ClosingExchangeStatus
    answer: str | None
    failure: str | None
    timestamp: datetime
    round_number: int


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


class AgentTokenUsageResponse(BaseModel):
    """Tokens the run's agents spent, summed over every response that recorded usage.

    ``reasoning_tokens`` is the part of ``output_tokens`` the models spent
    thinking, so a total across these fields reads ``output_tokens`` alone. It
    stays 0 for a provider that reports no reasoning breakdown, which is also
    what a model that did not think returns.
    """

    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


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
    agent_token_usage: AgentTokenUsageResponse
    duration_seconds: float
    status: RunStatus
    channel_ids: list[str]
    # The channels the scenario scores, from its own `get_primary_channels()`.
    # The round timeline filters to these; it used to read a hand-kept map in
    # the frontend, which is how three scenarios showed an empty timeline.
    primary_channel_ids: list[str]
    provider: str
    agents: list[AgentDetail]
    agent_swap_events: list[AgentSwapEventDTO]
    context_compaction_events: list[ContextCompactionEventDTO]
    messages: list[ChannelMessage]
    reasoning: list[ReasoningEntry]
    tool_use: list[ToolUseEntry]
    run_cycle_failures: list[AgentRunCycleFailedEntry]
    # The closing prompt each agent was sent once the run completed, in log
    # order. Empty for a run whose scenario sets no closing prompt.
    closing_exchanges: list[ClosingExchangeEntry]
    evaluation: EvalReportResponse | None
    evaluation_in_progress: bool
    has_eval_log_file: bool
    fork_source: ForkSource | None
    replace_agent_source: ReplaceAgentSource | None
    cross_run_replace_agent_source: CrossRunReplaceAgentSource | None
    fork_at_round_source: ForkAtRoundSource | None
    children: list[DerivedRunReference]
    labels: list[str]
    note: str | None
    round_endings: list[RoundEnding]
    round_results: list[RoundResult]
    round_injections: list[RoundInjection]
    # Events of types this server cannot parse for the run, in log order: its
    # scenario is not loaded here, or no longer declares them.
    unrecognized_events: list[UnrecognizedEventEntry]
    # Typed as the base so this model does not depend on which scenarios are
    # loaded; serialized as the subclass it holds. The API schema publishes the
    # union of every loaded scenario's extras (server/runs/scenario_openapi.py).
    scenario_extras: SerializeAsAny[ScenarioRunExtrasBase] | None


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
    """SSE event emitted when an agent joins the simulation.

    ``model_settings`` is absent from an event logged before the field existed,
    which carries the agent's output cap as ``max_tokens`` instead.
    """

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
    model_settings: AgentModelSettings | None = None
    max_tokens: int | None = None


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
    """SSE event emitted when the LLM returns a response: its text and exposed reasoning."""

    event_type: Literal["llm_response_received"]
    event_id: str
    timestamp: datetime
    agent_id: str
    thinking: str | None
    thinking_parts: list[ThinkingPartRecord]
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


PLATFORM_SSE_EVENT_TYPES: tuple[type[BaseModel], ...] = (
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

# The platform's SSE events. A scenario's run-detail extension can add its own;
# the app factory publishes the union with those in the API schema
# (server/runs/scenario_openapi.py).
_platform_sse_event_union: Any = Union[PLATFORM_SSE_EVENT_TYPES]
PlatformSSEEvent = Annotated[_platform_sse_event_union, Discriminator("event_type")]
