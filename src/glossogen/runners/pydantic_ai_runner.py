"""Pydantic AI agent runner using the pydantic-ai framework.

Launches a Pydantic AI agent that connects to the simulation runtime's
MCP server and participates autonomously in the scenario. Uses
``agent.run()`` with an ``event_stream_handler`` for accumulating
reasoning text and detecting tool call results.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterable, Awaitable, Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from langfuse import propagate_attributes
from pydantic_ai import Agent, _agent_graph
from pydantic_ai.agent import AgentRunResult as PydanticAIAgentRunResult
from pydantic_ai.agent.abstract import EventStreamHandler
from pydantic_ai.capabilities import AgentCapability, ProcessHistory
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import (
    AgentStreamEvent,
    CompactionPart,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
)
from pydantic_ai.models.anthropic import AnthropicCompaction
from pydantic_ai.models.openai import OpenAICompaction
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RequestUsage, RunUsage, UsageLimits
from pydantic_graph import End
from tenacity import RetryCallState, retry, stop_after_attempt

from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import (
    AgentResumed,
    AgentRunCycleFailed,
    ContextCompacted,
    LLMResponseReceived,
    ModelRequestCompleted,
    ToolCallInvoked,
    ToolResultReceived,
    VirtualRequestReleased,
    WaitRegistered,
)
from glossogen.models.event_base import TokenUsage
from glossogen.models.interaction_protocol import WaitKind, is_workspace_action_protocol
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.runners.agent_run_result import AgentRunResult
from glossogen.runners.agent_runner_base import AgentRunner
from glossogen.runners.communication_protocol import (
    COMPACTION_INSTRUCTIONS,
    build_full_system_prompt,
    interaction_prompts,
    render_implicit_finish_wake_prompt,
)
from glossogen.runners.context_budget_processor import ContextBudgetTrimmer
from glossogen.runners.history_cleanup_processor import clean_history
from glossogen.runners.pydantic_ai_model_factory import (
    build_pydantic_ai_model,
    default_pydantic_ai_settings,
)
from glossogen.runners.wait_suspension import (
    MIXED_WAIT_ERROR,
    WakePackage,
    build_wake_package,
    contains_wait_call,
    drain_lifecycle,
    error_return_request,
    package_json,
    parse_wait_arguments,
    tool_calls_of,
    wake_return_request,
)
from glossogen.runtime.scenario_mcp_tool import calling_agent_id
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.server.runs.streaming_event import AgentCostUpdated
from glossogen.telemetry_round_processor import current_round_source
from glossogen.token_pricing import compute_token_cost_usd, find_pricing

logger = logging.getLogger(__name__)

AGENT_RUN_RETRY_ATTEMPTS = 3


def _log_agent_run_retry(retry_state: RetryCallState) -> None:
    """Log each failed agent.run() attempt before tenacity retries."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "agent.run() attempt %d/%d failed with %s, retrying",
        retry_state.attempt_number,
        AGENT_RUN_RETRY_ATTEMPTS,
        type(exc).__name__ if exc else "unknown",
    )


def _log_task_exception(task: asyncio.Task[None]) -> None:
    """Log exceptions from fire-and-forget event logging tasks."""
    if not task.cancelled() and task.exception() is not None:
        logger.error("Background log task failed", exc_info=task.exception())


def _serialize_tool_result(content: object) -> str:
    """Serialize a tool result to a string, using JSON for dicts and lists."""
    if isinstance(content, (dict, list)):
        try:
            return json.dumps(content)  # pyright: ignore[reportUnknownArgumentType]
        except (TypeError, ValueError):
            logger.exception("Failed to JSON-serialize tool result, falling back to str()")
    return str(content)  # pyright: ignore[reportUnknownArgumentType]


class _StreamingState:
    """Mutable state shared between the event handler and the outer run loop.

    Tracks accumulated reasoning text, pending tool calls, and the
    ``got_done`` flag that signals the agent should stop looping.
    """

    def __init__(self) -> None:
        self.got_done = False
        self.pending_tool_calls: dict[str, ToolCallRequest] = {}
        self.accumulated_thinking = ""
        self.accumulated_text = ""
        self.accumulated_tool_calls: list[ToolCallRequest] = []
        self.accumulated_compaction = ""
        self.compaction_occurred = False
        self.compaction_has_details = False
        self.compaction_provider_name = "unknown"
        self.compaction_round = 0
        self.background_tasks: list[asyncio.Task[None]] = []

    def spawn_log_task(self, coro: object) -> None:
        """Create a fire-and-forget logging task and track it for later cleanup."""
        task: asyncio.Task[None] = asyncio.get_running_loop().create_task(coro)  # type: ignore[arg-type]
        task.add_done_callback(_log_task_exception)
        self.background_tasks.append(task)


@dataclass(frozen=True)
class _CycleOutcome:
    """How one ``agent.run`` cycle ended.

    ``completed`` is the ordinary end: the model answered with text. ``done`` is a
    termination delivered by a tool. ``suspended`` and ``rejected`` are the two
    ways a ``workspace_action`` suspension call (``wait_for_message`` or
    ``finish``) is intercepted before any tool runs: alone, the agent is parked;
    with siblings, every call is refused. Both
    carry the history ending in that response and its tool calls.
    """

    kind: Literal["completed", "done", "suspended", "rejected"]
    result: PydanticAIAgentRunResult[str] | None
    history: list[ModelMessage] | None
    tool_calls: list[ToolCallPart]


class _RunCheckpoint:
    """The latest point an agent run can resume from after a failed model request.

    A cycle can span a whole round of tool calls, so a retry that restarted from
    the cycle's input would discard every step taken since. Before each model
    request the runner records the history ending in that pending request, with
    no prompt. pydantic-ai re-sends a trailing ``ModelRequest`` when it is given
    no user prompt, so a retry resumes at the request that failed.
    """

    def __init__(self, messages: list[ModelMessage] | None, prompt: str | None) -> None:
        self.messages = messages
        self.prompt = prompt

    def save_pending_request(self, history: list[ModelMessage], request: ModelRequest) -> None:
        """Record ``history`` plus the request about to be sent as the resume point."""
        self.messages = [*history, request]
        self.prompt = None


@retry(
    stop=stop_after_attempt(AGENT_RUN_RETRY_ATTEMPTS),
    reraise=True,
    before_sleep=_log_agent_run_retry,
)
async def _run_agent_call(
    *,
    agent: Agent[None, str],
    checkpoint: _RunCheckpoint,
    event_stream_handler: EventStreamHandler[None],
    max_tokens: int,
    record_usage: Callable[[RunUsage], None],
    non_streaming_model_requests: bool,
    state: _StreamingState,
    flush_inter_call_response: Callable[[], None],
    stop_on_done: bool,
    intercept_wait: bool,
    on_model_response: Callable[[ModelResponse], None],
    before_model_request: Callable[[], None],
    gate_model_response: Callable[[ModelResponse], Awaitable[None]],
) -> _CycleOutcome:
    """Drive ``agent.iter`` so cumulative usage is captured even on cancellation.

    The supplied ``record_usage`` callback is invoked exactly once per call,
    on success, error, or cancellation, with the cumulative ``RunUsage`` for
    that attempt. This lets the caller flush a usage event for cycles that
    never reach a clean completion (e.g. when the supervisor cancels the
    agent task at scenario end).

    When ``non_streaming_model_requests`` is true, model-request nodes bypass
    pydantic-ai's streaming path and use the non-streaming ``model.request()``.
    This works around https://github.com/vllm-project/vllm/issues/31871, where
    vLLM's hermes tool parser leaks raw ``<tool_call>`` XML into the content
    field instead of populating ``tool_calls`` whenever ``stream=True``.
    Tool-execution nodes still stream so ``FunctionToolCallEvent`` /
    ``FunctionToolResultEvent`` continue to drive logging; text and thinking
    parts are accumulated directly from ``model_response.parts``.

    Each attempt starts from ``checkpoint`` and advances it before every model
    request, so a tenacity retry resumes at the failed request instead of
    replaying the cycle from its first prompt.

    ``on_model_response`` is called once per model response with that response,
    which carries the request's own usage. With ``intercept_wait`` set, a
    response calling ``wait_for_message`` or ``finish`` ends the cycle before any
    of its tools run: alone as ``suspended``, with siblings as ``rejected``.

    ``before_model_request`` runs as each model request is issued, and
    ``gate_model_response`` is awaited after ``on_model_response`` and before
    anything the response asked for runs. A virtual clock uses the pair to
    order responses by simulated latency; without one both return at once.
    """
    async with agent.iter(
        user_prompt=checkpoint.prompt,
        message_history=checkpoint.messages,
        usage_limits=UsageLimits(request_limit=None),
        model_settings=ModelSettings(max_tokens=max_tokens),
    ) as agent_run:
        try:
            node = agent_run.next_node
            last_seen_response: ModelResponse | None = None
            while not isinstance(node, End):
                if Agent.is_call_tools_node(node) and node.model_response is not last_seen_response:
                    last_seen_response = node.model_response
                    on_model_response(node.model_response)
                    await gate_model_response(node.model_response)
                    if intercept_wait and contains_wait_call(node.model_response):
                        calls = tool_calls_of(node.model_response)
                        kind: Literal["suspended", "rejected"] = "suspended"
                        if len(calls) != 1:
                            kind = "rejected"
                        return _CycleOutcome(
                            kind=kind,
                            result=None,
                            history=agent_run.all_messages(),
                            tool_calls=calls,
                        )
                if Agent.is_model_request_node(node):
                    before_model_request()
                    checkpoint.save_pending_request(
                        history=agent_run.all_messages(),
                        request=node.request,
                    )
                if Agent.is_model_request_node(node) and non_streaming_model_requests:
                    if state.accumulated_tool_calls:
                        flush_inter_call_response()
                    next_node = await agent_run.next(node)
                    if Agent.is_call_tools_node(next_node):
                        for part in next_node.model_response.parts:
                            if isinstance(part, TextPart):
                                state.accumulated_text += part.content
                            elif isinstance(part, ThinkingPart) and part.content:
                                state.accumulated_thinking += part.content
                    node = next_node
                    continue
                if Agent.is_model_request_node(node) or Agent.is_call_tools_node(node):
                    run_ctx = _agent_graph.build_run_context(agent_run.ctx)
                    async with node.stream(agent_run.ctx) as stream:
                        await event_stream_handler(run_ctx, stream)
                    if stop_on_done and state.got_done:
                        # A tool has delivered termination. Do not ask the model
                        # for another response just to persuade it to stop.
                        return _CycleOutcome(kind="done", result=None, history=None, tool_calls=[])
                node = await agent_run.next(node)
            assert agent_run.result is not None
            return _CycleOutcome(
                kind="completed", result=agent_run.result, history=None, tool_calls=[]
            )
        finally:
            record_usage(agent_run.usage)


class PydanticAIRunner(AgentRunner):
    """Runs a single Pydantic AI agent as an autonomous participant.

    Uses ``agent.run()`` with ``event_stream_handler`` so the agent
    executes all tool calls to completion while accumulating reasoning
    text and tool results for JSONL logging.
    """

    def __init__(
        self,
        max_turns: int,
        event_bus: EventBus,
        run_id: str,
        scenario_name: str,
        telemetry_enabled: bool,
    ) -> None:
        self._max_turns = max_turns
        self._event_bus = event_bus
        self._run_id = run_id
        self._scenario_name = scenario_name
        self._telemetry_enabled = telemetry_enabled

    def _agent_trace_context(self, agent_config: AgentConfig) -> AbstractContextManager[Any]:
        """Return a Langfuse attribute-propagation context for this agent's spans.

        Groups every agent in the simulation under one Langfuse session
        (``session_id`` = run id) and tags each span with the agent's identity.
        Returns a no-op context when telemetry is disabled so the run path adds
        no overhead.
        """
        if not self._telemetry_enabled:
            return nullcontext()
        return propagate_attributes(
            session_id=self._run_id,
            metadata={
                "agent_id": agent_config.agent_id,
                "role_name": agent_config.role_name,
                "model": agent_config.model,
                "provider": agent_config.provider,
                "scenario": self._scenario_name,
            },
            tags=[self._scenario_name, agent_config.provider, agent_config.model, "glossogen"],
        )

    async def start(
        self,
        agent_config: AgentConfig,
        mcp_server_url: str,
        mcp_server_object: Any,
        runtime: SimulationRuntime,
        cost_tracker: dict[str, float],
    ) -> AgentRunResult:
        """Launch a Pydantic AI agent that loops until it receives a done notification."""
        event_logger = runtime.event_logger
        agent_id = agent_config.agent_id
        provider = agent_config.provider
        if self._telemetry_enabled:
            # Round is global across agents; every runner points the telemetry
            # round source at the same live runtime value. The span processor
            # reads it when each generation span opens.
            current_round_source.set_provider(provider=lambda: runtime.current_round)
        logger.info(
            "Starting Pydantic AI agent %s (%s) max_turns=%d provider=%s model=%s",
            agent_id,
            agent_config.role_name,
            self._max_turns,
            provider,
            agent_config.model,
        )

        mcp_url = f"{mcp_server_url}?agent_id={agent_id}"
        # A run leaves this None and the toolset connects over Streamable HTTP.
        # A caller dispatching in-process passes the server object, and the
        # toolset talks to it in memory. Either way the same protocol, tools and
        # authorization guard run.
        calling_agent_id.set(agent_id)
        if mcp_server_object is None:
            mcp_toolset = MCPToolset(mcp_url)
        else:
            mcp_toolset = MCPToolset(mcp_server_object)

        full_system_prompt = build_full_system_prompt(
            base_prompt=agent_config.system_prompt,
            role_name=agent_config.role_name,
            interaction_protocol=agent_config.interaction_protocol,
            tool_names=agent_config.tool_names,
        )
        initial_prompt, continue_prompt = interaction_prompts(
            interaction_protocol=agent_config.interaction_protocol,
            tool_names=agent_config.tool_names,
        )
        stop_on_done = is_workspace_action_protocol(agent_config.interaction_protocol)

        capabilities: list[AgentCapability[None]] = [ProcessHistory(clean_history)]
        if agent_config.compaction.enabled:
            if provider == "anthropic":
                capabilities.append(
                    AnthropicCompaction(
                        token_threshold=agent_config.compaction.token_threshold,
                        instructions=COMPACTION_INSTRUCTIONS,
                    )
                )
            elif provider == "openai":
                capabilities.append(
                    OpenAICompaction(
                        token_threshold=agent_config.compaction.token_threshold,
                    )
                )
            elif provider == "self-hosted":
                trimmer = ContextBudgetTrimmer(
                    agent_id=agent_id,
                    token_threshold=agent_config.compaction.token_threshold,
                    thinking_in_requests=agent_config.send_back_thinking,
                )
                capabilities.append(ProcessHistory(trimmer.trim))

        intercept_wait = is_workspace_action_protocol(agent_config.interaction_protocol)
        agent: Agent[None, str] = Agent(
            model=build_pydantic_ai_model(
                model=agent_config.model,
                provider=provider,
                send_back_thinking=agent_config.send_back_thinking,
            ),
            deps_type=type(None),
            system_prompt=full_system_prompt,
            toolsets=[mcp_toolset],
            model_settings=default_pydantic_ai_settings(provider=provider),
            capabilities=capabilities,
        )

        # vLLM's hermes tool parser drops <tool_call> XML on the floor when
        # streaming (https://github.com/vllm-project/vllm/issues/31871), so the
        # self-hosted path runs model requests in non-streaming mode.
        non_streaming_model_requests = provider == "self-hosted"

        message_history: list[ModelMessage] | None = agent_config.initial_message_history
        total_input_tokens = 0
        total_output_tokens = 0
        total_cache_read_tokens = 0
        total_cache_write_tokens = 0
        total_turns = 0
        cumulative_cost = 0.0
        if message_history is not None:
            checkpoint = _RunCheckpoint(messages=message_history, prompt=continue_prompt)
        else:
            checkpoint = _RunCheckpoint(messages=None, prompt=initial_prompt)
        bus = self._event_bus
        all_background_tasks: list[asyncio.Task[None]] = []
        cycle_pricing = find_pricing(
            model=agent_config.model, provider=agent_config.provider, at=datetime.now(tz=UTC)
        )
        last_recorded_usage: RunUsage = RunUsage()

        try:
            async with mcp_toolset:
                while total_turns < self._max_turns:
                    state = _StreamingState()
                    captured_state = state

                    async def _handle_events(
                        _ctx: RunContext[None],  # pyright: ignore[reportUnusedParameter]
                        event_stream: AsyncIterable[AgentStreamEvent],
                    ) -> None:
                        """Consume streaming events from a single agent.run() cycle.

                        Accumulates reasoning text and tool call results for
                        JSONL logging, and detects the done signal.
                        """
                        async for event in event_stream:
                            self._process_stream_event(
                                agent_id=agent_id,
                                event=event,
                                state=captured_state,
                                event_logger=event_logger,
                                round_number=runtime.current_round,
                            )

                    last_recorded_usage = RunUsage()

                    def _record_usage(snapshot: RunUsage) -> None:
                        """Capture the per-cycle cumulative usage into the outer scope.

                        Called from ``_run_agent_call``'s finally block so cancellation
                        and errors still surface the partial usage that was accrued
                        before termination.
                        """
                        nonlocal last_recorded_usage
                        last_recorded_usage = snapshot

                    logger.debug(
                        "Agent %s starting cycle %d with prompt: %.100s",
                        agent_id,
                        total_turns + 1,
                        checkpoint.prompt,
                    )

                    def _flush_inter_call_response() -> None:
                        """Close out a prior tool_use response when the next model request begins.

                        Mirrors the streaming-mode behavior in
                        ``_process_stream_event`` where a fresh
                        ``PartStartEvent`` for a ``TextPart``/``ThinkingPart``
                        flushes the previously-accumulated tool calls.
                        """
                        self._flush_response_block(
                            agent_id=agent_id,
                            state=captured_state,
                            event_logger=event_logger,
                            stop_reason="tool_use",
                            round_number=runtime.current_round,
                        )

                    cycle_number = total_turns + 1
                    request_count = 0

                    def _record_model_response(response: ModelResponse) -> None:
                        """Log one request's own usage as it completes."""
                        nonlocal request_count
                        request_count += 1
                        captured_state.spawn_log_task(
                            event_logger.log(
                                event=ModelRequestCompleted(
                                    agent_id=agent_id,
                                    round_number=runtime.current_round,
                                    cycle=cycle_number,
                                    request_index=request_count,
                                    input_tokens=response.usage.input_tokens,
                                    output_tokens=response.usage.output_tokens,
                                    cache_read_input_tokens=response.usage.cache_read_tokens,
                                    cache_creation_input_tokens=response.usage.cache_write_tokens,
                                )
                            )
                        )

                    virtual_clock = runtime.virtual_clock

                    def _begin_model_request() -> None:
                        if virtual_clock is not None:
                            virtual_clock.begin_inference(agent_id=agent_id)

                    async def _gate_model_response(response: ModelResponse) -> None:
                        """Hold the response until virtual time reaches its simulated end.

                        The scenario then sees the response's usage, before its tools run.
                        """
                        usage = response.usage
                        if virtual_clock is not None:
                            await _wait_for_virtual_turn(usage=usage)
                        runtime.scenario.on_model_usage(
                            agent_id=agent_id,
                            input_tokens=usage.input_tokens,
                            output_tokens=usage.output_tokens,
                        )

                    async def _wait_for_virtual_turn(usage: RequestUsage) -> None:
                        """Wait for the virtual clock to release this response and log when."""
                        assert virtual_clock is not None
                        timing = await virtual_clock.complete_inference(
                            agent_id=agent_id,
                            output_tokens=usage.output_tokens,
                        )
                        captured_state.spawn_log_task(
                            event_logger.log(
                                event=VirtualRequestReleased(
                                    agent_id=agent_id,
                                    round_number=runtime.current_round,
                                    cycle=cycle_number,
                                    request_index=request_count,
                                    started_at_s=timing.started_at,
                                    completed_at_s=timing.completed_at,
                                    output_tokens=usage.output_tokens,
                                )
                            )
                        )

                    cycle_succeeded = False
                    outcome: _CycleOutcome | None = None
                    try:
                        with self._agent_trace_context(agent_config=agent_config):
                            outcome = await _run_agent_call(
                                agent=agent,
                                checkpoint=checkpoint,
                                event_stream_handler=_handle_events,
                                max_tokens=agent_config.max_tokens,
                                record_usage=_record_usage,
                                non_streaming_model_requests=non_streaming_model_requests,
                                state=captured_state,
                                flush_inter_call_response=_flush_inter_call_response,
                                stop_on_done=stop_on_done,
                                intercept_wait=intercept_wait,
                                on_model_response=_record_model_response,
                                before_model_request=_begin_model_request,
                                gate_model_response=_gate_model_response,
                            )
                        cycle_succeeded = True
                    except Exception as exc:
                        logger.exception(
                            "Agent %s run cycle %d failed, retrying",
                            agent_id,
                            total_turns + 1,
                        )
                        state.spawn_log_task(
                            event_logger.log(
                                event=AgentRunCycleFailed(
                                    agent_id=agent_id,
                                    round_number=runtime.current_round,
                                    cycle=total_turns + 1,
                                    error_type=type(exc).__name__,
                                    message=str(exc),
                                )
                            )
                        )
                    finally:
                        # Always accumulate whatever usage was captured during this
                        # attempt — successful, errored, or cancelled — so cost is
                        # tracked even when the agent task is killed mid-cycle by
                        # the supervisor at scenario end.
                        cycle_usage = last_recorded_usage
                        total_input_tokens += cycle_usage.input_tokens
                        total_output_tokens += cycle_usage.output_tokens
                        total_cache_read_tokens += cycle_usage.cache_read_tokens
                        total_cache_write_tokens += cycle_usage.cache_write_tokens
                        if cycle_pricing is not None:
                            cumulative_cost = compute_token_cost_usd(
                                pricing=cycle_pricing,
                                input_tokens=total_input_tokens,
                                output_tokens=total_output_tokens,
                                cache_read_tokens=total_cache_read_tokens,
                                cache_write_tokens=total_cache_write_tokens,
                            )
                            bus.publish(
                                event=AgentCostUpdated(
                                    agent_id=agent_id,
                                    cumulative_cost_usd=cumulative_cost,
                                ).model_dump(mode="json")
                            )
                            cost_tracker[agent_id] = cumulative_cost

                    if stop_on_done and state.got_done:
                        self._flush_response_block(
                            agent_id=agent_id,
                            state=state,
                            event_logger=event_logger,
                            stop_reason="tool_use",
                            round_number=runtime.current_round,
                            usage=TokenUsage(
                                input_tokens=cycle_usage.input_tokens,
                                output_tokens=cycle_usage.output_tokens,
                                cache_read_input_tokens=cycle_usage.cache_read_tokens,
                                cache_creation_input_tokens=cycle_usage.cache_write_tokens,
                            ),
                        )
                        all_background_tasks.extend(state.background_tasks)
                        total_turns += 1
                        break

                    if not cycle_succeeded or outcome is None:
                        # The checkpoint already holds the last pending request, so
                        # the next cycle resumes there with its history intact.
                        all_background_tasks.extend(state.background_tasks)
                        total_turns += 1
                        continue

                    cycle_token_usage = TokenUsage(
                        input_tokens=cycle_usage.input_tokens,
                        output_tokens=cycle_usage.output_tokens,
                        cache_read_input_tokens=cycle_usage.cache_read_tokens,
                        cache_creation_input_tokens=cycle_usage.cache_write_tokens,
                    )
                    if outcome.kind in ("suspended", "rejected"):
                        assert outcome.history is not None
                        checkpoint, terminated = await self._handle_intercepted_wait(
                            agent_id=agent_id,
                            runtime=runtime,
                            outcome=outcome,
                            state=state,
                            event_logger=event_logger,
                            usage=cycle_token_usage,
                        )
                        all_background_tasks.extend(state.background_tasks)
                        total_turns += 1
                        if terminated:
                            logger.info(
                                "Agent %s run ended while parked, after %d turns",
                                agent_id,
                                total_turns,
                            )
                            break
                        continue

                    result = outcome.result
                    assert result is not None
                    checkpoint = _RunCheckpoint(
                        messages=result.all_messages(),
                        prompt=continue_prompt,
                    )
                    total_turns += 1

                    # Safety net: flush a compaction block that had no following
                    # generation part this cycle (it normally closes when the response
                    # part after the compaction starts, in _process_stream_event).
                    self._flush_compaction_summary(
                        agent_id=agent_id, event_logger=event_logger, state=state
                    )

                    logger.info(
                        "Agent %s cycle %d complete: in=%d out=%d "
                        "cache_read=%d cache_write=%d tokens",
                        agent_id,
                        total_turns,
                        cycle_usage.input_tokens,
                        cycle_usage.output_tokens,
                        cycle_usage.cache_read_tokens,
                        cycle_usage.cache_write_tokens,
                    )

                    # Log any remaining reasoning + tool calls from the final response
                    self._flush_response_block(
                        agent_id=agent_id,
                        state=state,
                        event_logger=event_logger,
                        stop_reason="end_turn",
                        round_number=runtime.current_round,
                        usage=TokenUsage(
                            input_tokens=cycle_usage.input_tokens,
                            output_tokens=cycle_usage.output_tokens,
                            cache_read_input_tokens=cycle_usage.cache_read_tokens,
                            cache_creation_input_tokens=cycle_usage.cache_write_tokens,
                        ),
                    )

                    all_background_tasks.extend(state.background_tasks)

                    if state.got_done:
                        logger.info(
                            "Agent %s received done notification after %d turns, stopping",
                            agent_id,
                            total_turns,
                        )
                        break

                    if intercept_wait:
                        # A workspace turn that ended in text counts as finish; the
                        # wake is delivered as the next user prompt because there
                        # is no call to answer.
                        package = await self._park_until_wake(
                            agent_id=agent_id,
                            runtime=runtime,
                            kind="finish",
                            deadline_s=None,
                            implicit=True,
                            state=state,
                            event_logger=event_logger,
                        )
                        all_background_tasks.extend(state.background_tasks)
                        if package.terminated:
                            logger.info(
                                "Agent %s run ended while parked after a text turn (%d turns)",
                                agent_id,
                                total_turns,
                            )
                            break
                        checkpoint = _RunCheckpoint(
                            messages=result.all_messages(),
                            prompt=render_implicit_finish_wake_prompt(
                                package_json=package_json(package=package),
                                tool_names=agent_config.tool_names,
                            ),
                        )

                if total_turns >= self._max_turns:
                    logger.warning(
                        "Agent %s hit max_turns limit (%d), stopping",
                        agent_id,
                        self._max_turns,
                    )
        except Exception:
            logger.exception("Agent %s Pydantic AI run failed", agent_id)
            raise
        finally:
            runtime.wait_registry.cancel(agent_id=agent_id)
            if runtime.virtual_clock is not None:
                runtime.virtual_clock.retire(agent_id=agent_id)
            # Wait for all background logging tasks to finish so no events are lost.
            pending = [t for t in all_background_tasks if not t.done()]
            if pending:
                logger.debug(
                    "Agent %s waiting for %d background log tasks",
                    agent_id,
                    len(pending),
                )
                await asyncio.gather(*pending, return_exceptions=True)

        logger.info(
            "Agent %s finished. Total turns: %d, total cost: $%.4f",
            agent_id,
            total_turns,
            cumulative_cost,
        )

        return AgentRunResult(
            agent_id=agent_id,
            total_cost_usd=cumulative_cost,
            total_turns=total_turns,
        )

    async def _handle_intercepted_wait(
        self,
        agent_id: str,
        runtime: SimulationRuntime,
        outcome: _CycleOutcome,
        state: _StreamingState,
        event_logger: EventLogger,
        usage: TokenUsage,
    ) -> tuple[_RunCheckpoint, bool]:
        """Answer an intercepted response and return where the next cycle resumes.

        The response's calls were never executed, so they are logged here as
        invoked, then answered: every call with the rejection text when the
        suspension call had siblings, the single call with its wake package
        otherwise. The
        checkpoint ends in the answering request and carries no prompt, so the
        next cycle re-sends that request. Returns ``terminated`` True when the
        wake carried the run's end, in which case no further cycle should run.
        """
        assert outcome.history is not None
        round_number = runtime.current_round
        for call in outcome.tool_calls:
            request = ToolCallRequest(
                call_id=call.tool_call_id,
                tool_name=call.tool_name,
                arguments=call.args_as_dict(),
            )
            state.accumulated_tool_calls.append(request)
            state.spawn_log_task(
                event_logger.log(
                    ToolCallInvoked(
                        agent_id=agent_id,
                        call_id=request.call_id,
                        tool_name=request.tool_name,
                        arguments=request.arguments,
                        round_number=round_number,
                    )
                )
            )
        self._flush_response_block(
            agent_id=agent_id,
            state=state,
            event_logger=event_logger,
            stop_reason="wait" if outcome.kind == "suspended" else "tool_use",
            round_number=round_number,
            usage=usage,
        )

        def _log_results(text: str) -> None:
            for call in outcome.tool_calls:
                state.spawn_log_task(
                    event_logger.log(
                        ToolResultReceived(
                            agent_id=agent_id,
                            tool_name=call.tool_name,
                            call_id=call.tool_call_id,
                            arguments=call.args_as_dict(),
                            result=text,
                            round_number=round_number,
                        )
                    )
                )

        if outcome.kind == "rejected":
            logger.info(
                "Agent %s combined a suspension call with %d other tool call(s); none executed",
                agent_id,
                len(outcome.tool_calls) - 1,
            )
            _log_results(text=MIXED_WAIT_ERROR)
            request_message = error_return_request(
                tool_calls=outcome.tool_calls, error=MIXED_WAIT_ERROR
            )
            return _RunCheckpoint(messages=[*outcome.history, request_message], prompt=None), False

        call = outcome.tool_calls[0]
        try:
            wait_request = parse_wait_arguments(part=call)
        except ValueError as exc:
            logger.exception("Agent %s wait call rejected", agent_id)
            error = f"Rejected: {exc}"
            _log_results(text=error)
            request_message = error_return_request(tool_calls=[call], error=error)
            return _RunCheckpoint(messages=[*outcome.history, request_message], prompt=None), False

        package = await self._park_until_wake(
            agent_id=agent_id,
            runtime=runtime,
            kind=wait_request.kind,
            deadline_s=wait_request.deadline_s,
            implicit=False,
            state=state,
            event_logger=event_logger,
        )
        _log_results(text=package_json(package=package))
        if package.terminated:
            return _RunCheckpoint(messages=outcome.history, prompt=None), True
        return (
            _RunCheckpoint(
                messages=[*outcome.history, wake_return_request(tool_call=call, package=package)],
                prompt=None,
            ),
            False,
        )

    @staticmethod
    async def _park_until_wake(
        agent_id: str,
        runtime: SimulationRuntime,
        kind: WaitKind,
        deadline_s: float | None,
        implicit: bool,
        state: _StreamingState,
        event_logger: EventLogger,
    ) -> WakePackage:
        """Register the wait, sleep until it resumes, and build the wake package.

        No model request is made while parked. On resume the session's queued
        lifecycle notifications are drained into the package and the scenario
        renders the workspace part through its own delivery path.
        """
        session = runtime.resolve_session(agent_id=agent_id)
        wait = runtime.wait_registry.register(
            agent_id=agent_id,
            round_id=runtime.current_round,
            kind=kind,
            deadline_s=deadline_s,
            implicit=implicit,
        )
        state.spawn_log_task(
            event_logger.log(
                event=WaitRegistered(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    wait_id=wait.wait_id,
                    kind=kind,
                    deadline_s=deadline_s,
                    implicit=implicit,
                    message_cursors={
                        channel_id: session.get_last_seen_count(channel_id=channel_id)
                        for channel_id in runtime.channel_router.get_agent_channel_ids(
                            agent_id=agent_id
                        )
                    },
                )
            )
        )
        logger.info(
            "Agent %s parked (%s) on %s, deadline %s",
            agent_id,
            wait.wait_id,
            kind,
            deadline_s,
        )
        signal = await runtime.wait_registry.wait_for_resume(wait=wait)
        lifecycle = drain_lifecycle(session=session)
        workspace = await runtime.scenario.deliver_wake_context(
            agent_id=agent_id,
            wake_reasons=[reason.value for reason in signal.reasons],
        )
        package = build_wake_package(
            reasons=signal.reasons,
            round_number=runtime.current_round,
            waited_seconds=signal.waited_seconds,
            workspace=workspace,
            lifecycle=lifecycle,
        )
        state.spawn_log_task(
            event_logger.log(
                event=AgentResumed(
                    agent_id=agent_id,
                    round_number=runtime.current_round,
                    wait_id=wait.wait_id,
                    wake_reasons=package.wake_reasons,
                    waited_seconds=package.waited_seconds,
                    lifecycle_types=[entry.type for entry in lifecycle],
                    terminated=package.terminated,
                    wake_package=package.model_dump(),
                )
            )
        )
        return package

    def _flush_compaction_summary(
        self,
        agent_id: str,
        event_logger: EventLogger,
        state: _StreamingState,
    ) -> None:
        """Emit a ContextCompacted for a completed compaction block, then reset it.

        No-op unless a compaction block is currently open. Called when the block
        ends, meaning when the generated response (text/thinking/tool call) that
        follows the compaction starts, or at agent-cycle end for a trailing block.
        The event's round is ``state.compaction_round`` (recorded when the block
        started), so it reflects when compaction actually fired. Agent cycles span
        many rounds, so flushing at cycle end with the current round would
        mis-attribute it. The summary text is accumulated across the block's
        per-delta ``CompactionPart`` events (which the parts manager overwrites
        rather than accumulates, and which can span multiple streams); it may be
        empty when a real compaction returns no readable text, as with OpenAI, which
        fires compaction but keeps the summary encrypted server-side (content None)
        while carrying the compaction payload in ``provider_details``. Such a block
        is still recorded (empty ``summary_text``) because it did compact; only a
        genuine no-op (no text AND no provider_details, e.g. Anthropic reporting a
        compaction attempt that produced nothing) is dropped. Each block emits at
        most one event.
        """
        if not state.compaction_occurred:
            return
        summary_text = state.accumulated_compaction
        if not summary_text and not state.compaction_has_details:
            # Genuine no-op: a compaction attempt that produced neither a summary nor
            # round-trippable payload. Nothing happened, so record nothing.
            self._reset_compaction(state)
            return
        summary_char_count = len(summary_text)
        logger.info(
            "Agent %s context compacted by %s in round %d: %d-char summary: %.200s",
            agent_id,
            state.compaction_provider_name,
            state.compaction_round,
            summary_char_count,
            summary_text,
        )
        state.spawn_log_task(
            event_logger.log(
                event=ContextCompacted(
                    agent_id=agent_id,
                    round_number=state.compaction_round,
                    provider_name=state.compaction_provider_name,
                    summary_char_count=summary_char_count,
                    summary_text=summary_text,
                )
            )
        )
        self._reset_compaction(state)

    @staticmethod
    def _reset_compaction(state: _StreamingState) -> None:
        """Clear the per-compaction-block accumulator after a block is handled."""
        state.compaction_occurred = False
        state.compaction_has_details = False
        state.accumulated_compaction = ""
        state.compaction_provider_name = "unknown"

    def _flush_response_block(
        self,
        agent_id: str,
        state: _StreamingState,
        event_logger: EventLogger,
        stop_reason: str,
        round_number: int,
        usage: TokenUsage | None = None,
    ) -> None:
        """Log accumulated thinking + text + tool calls as one LLMResponseReceived event."""
        thinking = state.accumulated_thinking.strip()
        text = state.accumulated_text.strip()
        tool_calls = list(state.accumulated_tool_calls)
        if not thinking and not text and not tool_calls:
            return
        if usage is None:
            usage = TokenUsage(
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
        logger.info(
            "Agent %s reasoning: %.200s",
            agent_id,
            text,
        )
        state.spawn_log_task(
            event_logger.log(
                LLMResponseReceived(
                    agent_id=agent_id,
                    thinking=thinking if thinking else None,
                    text=text if text else None,
                    tool_calls=tool_calls,
                    stop_reason=stop_reason,
                    usage=usage,
                    round_number=round_number,
                )
            )
        )
        state.accumulated_thinking = ""
        state.accumulated_text = ""
        state.accumulated_tool_calls = []

    def _process_stream_event(
        self,
        agent_id: str,
        event: AgentStreamEvent,
        state: _StreamingState,
        event_logger: EventLogger,
        round_number: int,
    ) -> None:
        """Route a single streaming event to the appropriate handler.

        Pydantic AI emits four event types during an agent run cycle:

        - ``PartStartEvent``: A new content part (text, thinking, or tool call)
          begins in the model response.
        - ``PartDeltaEvent``: An incremental fragment of a content part (text
          token or thinking token).
        - ``FunctionToolCallEvent``: A tool call is fully assembled and about
          to be executed by the framework.
        - ``FunctionToolResultEvent``: The MCP server returned a result for a
          tool call. The done-detection logic inspects ``read_notifications``
          results here: if the serialized result contains ``"type": "done"``
          the agent's loop will terminate after the current cycle.
        """
        if isinstance(event, PartStartEvent):
            logger.debug(
                "Agent %s PartStart index=%d part_type=%s",
                agent_id,
                event.index,
                type(event.part).__name__,
            )
            if isinstance(event.part, (TextPart, ThinkingPart)):
                # Real generated content follows the compaction block, so close it now.
                self._flush_compaction_summary(
                    agent_id=agent_id, event_logger=event_logger, state=state
                )
                # A new text/thinking part is starting. If we have accumulated
                # tool calls from a previous response, flush them now so each
                # model response is logged as one thinking+text+tools block.
                if state.accumulated_tool_calls:
                    self._flush_response_block(
                        agent_id=agent_id,
                        state=state,
                        event_logger=event_logger,
                        stop_reason="tool_use",
                        round_number=round_number,
                    )
                if event.part.content:
                    if isinstance(event.part, ThinkingPart):
                        state.accumulated_thinking += event.part.content
                    else:
                        state.accumulated_text += event.part.content
            elif isinstance(event.part, CompactionPart):
                # Anthropic streams the compaction summary as multiple deltas, each
                # re-emitted here as a fresh CompactionPart carrying only that delta's
                # slice (the parts manager overwrites, never accumulates), and the
                # block can span more than one model-request stream. Accumulate the
                # slices across the whole block and flush it only when a non-compaction
                # part follows (below) or the cycle ends — never at stream end, which
                # would split the block. Record the round at block start so the event
                # reflects when compaction fired (agent cycles span many rounds).
                # OpenAI keeps the summary encrypted server-side (content is None) but
                # carries the compaction data in provider_details, so a real OpenAI
                # compaction has no text yet must still be recorded; track
                # provider_details so the flush can distinguish it from a genuine
                # Anthropic no-op (content None, no data).
                if not state.compaction_occurred:
                    state.compaction_occurred = True
                    state.compaction_round = round_number
                if isinstance(event.part.content, str):
                    state.accumulated_compaction += event.part.content
                if event.part.provider_details:
                    state.compaction_has_details = True
                if event.part.provider_name is not None:
                    state.compaction_provider_name = event.part.provider_name

        elif isinstance(event, PartDeltaEvent):
            if isinstance(event.delta, TextPartDelta):
                state.accumulated_text += event.delta.content_delta
            elif isinstance(event.delta, ThinkingPartDelta):
                if event.delta.content_delta:
                    state.accumulated_thinking += event.delta.content_delta

        elif isinstance(event, FunctionToolCallEvent):
            # A tool call is the generated response following a compaction block;
            # close the block now (case where the response has no text part).
            self._flush_compaction_summary(
                agent_id=agent_id, event_logger=event_logger, state=state
            )
            logger.debug(
                "Agent %s FunctionToolCall: %s (call_id=%s)",
                agent_id,
                event.part.tool_name,
                event.part.tool_call_id,
            )

            raw_args = event.part.args
            args: dict[str, Any] = {}
            if isinstance(raw_args, dict):
                args = raw_args
            elif isinstance(raw_args, str):
                try:
                    parsed = json.loads(raw_args)
                    if isinstance(parsed, dict):
                        args = cast(dict[str, Any], parsed)
                except json.JSONDecodeError:
                    pass
            tc_req = ToolCallRequest(
                call_id=event.part.tool_call_id,
                tool_name=event.part.tool_name,
                arguments=args,
            )
            state.accumulated_tool_calls.append(tc_req)
            state.pending_tool_calls[event.part.tool_call_id] = tc_req
            state.spawn_log_task(
                event_logger.log(
                    ToolCallInvoked(
                        agent_id=agent_id,
                        call_id=tc_req.call_id,
                        tool_name=tc_req.tool_name,
                        arguments=tc_req.arguments,
                        round_number=round_number,
                    )
                )
            )
            logger.info(
                "Agent %s tool call: %s(%s)",
                agent_id,
                event.part.tool_name,
                event.part.args,
            )

        elif isinstance(event, FunctionToolResultEvent):
            result_content = _serialize_tool_result(content=event.part.content)
            logger.debug(
                "Agent %s FunctionToolResult call_id=%s content=%.200s",
                agent_id,
                event.tool_call_id,
                result_content,
            )
            matched = state.pending_tool_calls.pop(event.tool_call_id, None)
            if matched is not None:
                state.spawn_log_task(
                    event_logger.log(
                        ToolResultReceived(
                            agent_id=agent_id,
                            tool_name=matched.tool_name,
                            call_id=matched.call_id,
                            arguments=matched.arguments,
                            result=result_content,
                            round_number=round_number,
                        )
                    )
                )
            self._detect_done_signal(
                agent_id=agent_id,
                matched=matched,
                result_content=result_content,
                state=state,
            )

    def _detect_done_signal(
        self,
        agent_id: str,
        matched: ToolCallRequest | None,
        result_content: str,
        state: _StreamingState,
    ) -> None:
        """Check whether a read_notifications tool result contains a done notification.

        The MCP server's ``read_notifications`` tool returns a JSON object with a
        ``"type"`` field. When ``type`` is ``"done"``, the simulation is over
        and the agent should stop after the current cycle. We detect this by
        checking whether the string representation of the result contains
        ``"type": "done"`` or ``'type': 'done'`` (the latter covers Python
        repr serialization of dicts).
        """
        if matched is None:
            return
        if not matched.tool_name.endswith("read_notifications"):
            return
        if '"type": "done"' in result_content or "'type': 'done'" in result_content:
            logger.info(
                "Agent %s read_notifications returned done signal",
                agent_id,
            )
            state.got_done = True
