"""Pydantic AI agent runner using the pydantic-ai framework.

Launches a Pydantic AI agent that connects to the simulation runtime's
MCP server and participates autonomously in the scenario. Drives
``agent.iter`` with an ``event_stream_handler`` that accumulates
reasoning text and tool calls for the event log.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterable, Awaitable, Callable
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from typing import Any, NamedTuple, cast

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
)
from pydantic_ai.models.anthropic import AnthropicCompaction
from pydantic_ai.models.openai import OpenAICompaction
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage, UsageLimits
from pydantic_graph import End
from tenacity import RetryCallState, retry, stop_after_attempt, wait_exponential

from glossogen.event_bus import EventBus
from glossogen.event_logger import EventLogger
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import (
    AgentRunCycleFailed,
    ContextCompacted,
    LLMResponseReceived,
    ToolCallInvoked,
    ToolResultReceived,
)
from glossogen.models.event_base import TokenUsage
from glossogen.models.tool_definition import ToolCallRequest
from glossogen.runners.agent_run_result import AgentRunResult
from glossogen.runners.agent_runner_base import AgentRunner
from glossogen.runners.communication_protocol import (
    COMPACTION_INSTRUCTIONS,
    build_full_system_prompt,
    runner_prompts_for,
)
from glossogen.runners.history_cleanup_processor import clean_history
from glossogen.runners.pydantic_ai_model_factory import (
    build_pydantic_ai_model,
    default_pydantic_ai_settings,
)
from glossogen.runners.read_notifications_tool import RunTermination, build_read_notifications_tool
from glossogen.runtime.scenario_mcp_tool import calling_agent_id
from glossogen.runtime.simulation_state import SimulationRuntime
from glossogen.server.runs.streaming_event import AgentCostUpdated
from glossogen.telemetry_round_processor import current_round_source
from glossogen.token_pricing import compute_token_cost_usd, find_pricing

logger = logging.getLogger(__name__)

AGENT_RUN_RETRY_ATTEMPTS = 3
AGENT_RUN_RETRY_BACKOFF_S = 1.0
"""The pause before the second attempt; each later pause doubles."""
AGENT_RUN_RETRY_MAX_BACKOFF_S = 30.0


def _log_agent_run_retry(retry_state: RetryCallState) -> None:
    """Log a failed attempt, with its error, before tenacity pauses and retries."""
    outcome = retry_state.outcome
    if outcome is None or not outcome.failed:
        return
    exc = outcome.exception()
    pause_s = 0.0
    if retry_state.next_action is not None:
        pause_s = retry_state.next_action.sleep
    logger.warning(
        "Model request attempt %d/%d failed with %s: %s; retrying in %.1fs",
        retry_state.attempt_number,
        AGENT_RUN_RETRY_ATTEMPTS,
        type(exc).__name__,
        exc,
        pause_s,
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


class _AttemptMark(NamedTuple):
    """How much of each accumulator was already present when an attempt began."""

    thinking: int
    text: int
    tool_calls: int


class _StreamingState:
    """Mutable state shared between the event handler and the outer run loop.

    Tracks accumulated reasoning text and pending tool calls. Whether the
    agent should stop is ``RunTermination``'s, set by ``read_notifications``.
    """

    def __init__(self) -> None:
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
        self._attempt_mark = _AttemptMark(thinking=0, text=0, tool_calls=0)

    def mark_attempt_start(self) -> None:
        """Remember how much is accumulated, so a failed attempt's share can be dropped."""
        self._attempt_mark = _AttemptMark(
            thinking=len(self.accumulated_thinking),
            text=len(self.accumulated_text),
            tool_calls=len(self.accumulated_tool_calls),
        )

    def discard_since_attempt_start(self) -> None:
        """Drop what the current attempt accumulated and has not logged."""
        mark = self._attempt_mark
        self.accumulated_thinking = self.accumulated_thinking[: mark.thinking]
        self.accumulated_text = self.accumulated_text[: mark.text]
        del self.accumulated_tool_calls[mark.tool_calls :]

    def spawn_log_task(self, coro: object) -> None:
        """Create a fire-and-forget logging task and track it for later cleanup."""
        task: asyncio.Task[None] = asyncio.get_running_loop().create_task(coro)  # type: ignore[arg-type]
        task.add_done_callback(_log_task_exception)
        self.background_tasks.append(task)


class _RunCheckpoint:
    """The latest point an agent run can resume from after a failed model request.

    A cycle can span a whole round of tool calls, so a retry that restarted from
    the cycle's input would execute every tool call made since a second time.
    Before each model request the runner records the history ending in that
    pending request, with no prompt. pydantic-ai re-sends a trailing
    ``ModelRequest`` when it is given no user prompt, so a retry resumes at the
    request that failed.
    """

    def __init__(self, messages: list[ModelMessage] | None, prompt: str | None) -> None:
        self.messages = messages
        self.prompt = prompt

    def save_pending_request(self, history: list[ModelMessage], request: ModelRequest) -> None:
        """Record ``history`` plus the request about to be sent as the resume point."""
        self.messages = [*history, request]
        self.prompt = None


def _restart_checkpoint(
    history: list[ModelMessage] | None, initial: str, continuation: str
) -> _RunCheckpoint:
    """Where a cycle starts after the previous one failed every retry.

    The last completed cycle's history with the continuation prompt, or the
    initial prompt when no cycle has completed yet.
    """
    if history is None:
        return _RunCheckpoint(messages=None, prompt=initial)
    return _RunCheckpoint(messages=history, prompt=continuation)


@retry(
    stop=stop_after_attempt(AGENT_RUN_RETRY_ATTEMPTS),
    wait=wait_exponential(multiplier=AGENT_RUN_RETRY_BACKOFF_S, max=AGENT_RUN_RETRY_MAX_BACKOFF_S),
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
    before_model_request: Callable[[], None],
    gate_model_response: Callable[[ModelResponse], Awaitable[None]],
) -> PydanticAIAgentRunResult[str]:
    """Drive ``agent.iter`` so cumulative usage is captured even on cancellation.

    ``record_usage`` is invoked once per attempt, from a ``finally`` block, with
    that attempt's cumulative ``RunUsage``, so the caller sees the usage of a
    cycle that never reaches a clean completion (the supervisor cancelling the
    agent task at scenario end, or an attempt that raised).

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
    replaying the cycle from its first prompt. A failure after a response
    arrived, in ``gate_model_response``, in the event handler or in a tool,
    resumes at the request that produced that response, which is sent again.
    Whatever the failed attempt accumulated in ``state`` and had not logged yet
    is discarded, so the retried response is logged once.

    ``before_model_request`` runs as each model request is issued, and
    ``gate_model_response`` is awaited once per response before anything the
    response asked for runs.
    """
    state.mark_attempt_start()
    async with agent.iter(
        user_prompt=checkpoint.prompt,
        message_history=checkpoint.messages,
        usage_limits=UsageLimits(request_limit=None),
        model_settings=ModelSettings(max_tokens=max_tokens),
    ) as agent_run:
        try:
            node = agent_run.next_node
            last_gated_response: ModelResponse | None = None
            while not isinstance(node, End):
                if (
                    Agent.is_call_tools_node(node)
                    and node.model_response is not last_gated_response
                ):
                    last_gated_response = node.model_response
                    await gate_model_response(node.model_response)
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
                node = await agent_run.next(node)
            assert agent_run.result is not None
            return agent_run.result
        except Exception:
            state.discard_since_attempt_start()
            raise
        finally:
            record_usage(agent_run.usage)


class PydanticAIRunner(AgentRunner):
    """Runs a single Pydantic AI agent as an autonomous participant.

    Drives ``agent.iter`` with an ``event_stream_handler``, so the agent
    executes all tool calls to completion while reasoning text and tool
    results are accumulated for JSONL logging.
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
        all_background_tasks: list[asyncio.Task[None]] = []
        try:

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

            runner_prompts = runner_prompts_for(
                role_name=agent_config.role_name,
                replacement=runtime.scenario.runner_prompts(agent_id=agent_id),
            )
            full_system_prompt = build_full_system_prompt(
                base_prompt=agent_config.system_prompt, prompts=runner_prompts
            )

            termination = RunTermination()
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

            agent: Agent[None, str] = Agent(
                model=build_pydantic_ai_model(model=agent_config.model, provider=provider),
                deps_type=type(None),
                system_prompt=full_system_prompt,
                toolsets=[mcp_toolset],
                tools=[
                    build_read_notifications_tool(
                        runtime=runtime, agent_id=agent_id, termination=termination
                    )
                ],
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
            last_completed_history = message_history
            if message_history is not None:
                checkpoint = _RunCheckpoint(
                    messages=message_history, prompt=runner_prompts.continuation
                )
            else:
                checkpoint = _RunCheckpoint(messages=None, prompt=runner_prompts.initial)
            bus = self._event_bus
            cycle_pricing = find_pricing(
                model=agent_config.model, provider=agent_config.provider, at=datetime.now(tz=UTC)
            )

            def _before_model_request() -> None:
                runtime.scenario.on_model_request_started(agent_id=agent_id)

            async def _gate_model_response(response: ModelResponse) -> None:
                await runtime.scenario.gate_model_response(
                    agent_id=agent_id,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                )

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
                        JSONL logging.
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
                        """Add one attempt's usage to the cycle's.

                        Called from ``_run_agent_call``'s finally block once per
                        attempt, so cancellation and errors still surface the usage
                        accrued before termination. A retried attempt resumes at the
                        failed request rather than repeating the earlier ones, so
                        each attempt's requests are counted once, by adding.
                        """
                        nonlocal last_recorded_usage
                        last_recorded_usage = last_recorded_usage + snapshot

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
                            usage=None,
                        )

                    cycle_succeeded = False
                    result: PydanticAIAgentRunResult[str] | None = None
                    try:
                        with self._agent_trace_context(agent_config=agent_config):
                            result = await _run_agent_call(
                                agent=agent,
                                checkpoint=checkpoint,
                                event_stream_handler=_handle_events,
                                max_tokens=agent_config.max_tokens,
                                record_usage=_record_usage,
                                non_streaming_model_requests=non_streaming_model_requests,
                                state=captured_state,
                                flush_inter_call_response=_flush_inter_call_response,
                                before_model_request=_before_model_request,
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
                        # Runs whether the cycle succeeded, raised or was cancelled, so
                        # every attempt's usage is counted and the cycle's logging
                        # tasks are awaited before the runner returns.
                        all_background_tasks.extend(state.background_tasks)
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

                    if not cycle_succeeded or result is None:
                        # Every retry resumed at the failed request and still failed,
                        # so re-sending it would fail the same way. Restart from the
                        # last completed cycle, as a fresh cycle.
                        checkpoint = _restart_checkpoint(
                            history=last_completed_history,
                            initial=runner_prompts.initial,
                            continuation=runner_prompts.continuation,
                        )
                        total_turns += 1
                        continue

                    last_completed_history = result.all_messages()

                    checkpoint = _RunCheckpoint(
                        messages=result.all_messages(),
                        prompt=runner_prompts.continuation,
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

                    if termination.is_set:
                        logger.info(
                            "Agent %s received done notification after %d turns, stopping",
                            agent_id,
                            total_turns,
                        )
                        break

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
            runtime.scenario.on_agent_retired(agent_id=agent_id)
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
        usage: TokenUsage | None,
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
        state.mark_attempt_start()

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
        - ``FunctionToolResultEvent``: A tool call returned its result. Whether
          the run is over for the agent is ``RunTermination``'s, set by the
          ``read_notifications`` tool, not read from the result here.
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
                        usage=None,
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
                # part follows (below) or the cycle ends, never at stream end, which
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
                    logger.exception(
                        "Agent %s tool call %s arguments are not JSON; logging them empty",
                        agent_id,
                        event.part.tool_name,
                    )
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
