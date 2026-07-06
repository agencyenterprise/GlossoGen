"""Pydantic AI agent runner using the pydantic-ai framework.

Launches a Pydantic AI agent that connects to the simulation runtime's
MCP server and participates autonomously in the scenario. Uses
``agent.run()`` with an ``event_stream_handler`` for accumulating
reasoning text and detecting tool call results.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterable, Callable
from typing import Any, cast

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
from tenacity import RetryCallState, retry, stop_after_attempt

from schmidt.event_bus import EventBus
from schmidt.event_logger import EventLogger
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import (
    AgentRunCycleFailed,
    ContextCompacted,
    LLMResponseReceived,
    ToolCallInvoked,
    ToolResultReceived,
)
from schmidt.models.event_base import TokenUsage
from schmidt.models.tool_definition import ToolCallRequest
from schmidt.runners.agent_run_result import AgentRunResult
from schmidt.runners.agent_runner_base import AgentRunner
from schmidt.runners.communication_protocol import (
    COMPACTION_INSTRUCTIONS,
    CONTINUE_PROMPT,
    INITIAL_PROMPT,
    build_full_system_prompt,
)
from schmidt.runners.history_cleanup_processor import clean_history
from schmidt.runners.pydantic_ai_model_factory import (
    build_pydantic_ai_model,
    default_pydantic_ai_settings,
)
from schmidt.runtime.simulation_state import SimulationRuntime
from schmidt.server.runs.streaming_event import AgentCostUpdated
from schmidt.token_pricing import find_pricing

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
        self.background_tasks: list[asyncio.Task[None]] = []

    def spawn_log_task(self, coro: object) -> None:
        """Create a fire-and-forget logging task and track it for later cleanup."""
        task: asyncio.Task[None] = asyncio.get_running_loop().create_task(coro)  # type: ignore[arg-type]
        task.add_done_callback(_log_task_exception)
        self.background_tasks.append(task)


@retry(
    stop=stop_after_attempt(AGENT_RUN_RETRY_ATTEMPTS),
    reraise=True,
    before_sleep=_log_agent_run_retry,
)
async def _run_agent_call(
    *,
    agent: Agent[None, str],
    prompt: str,
    message_history: list[ModelMessage] | None,
    event_stream_handler: EventStreamHandler[None],
    max_tokens: int,
    record_usage: Callable[[RunUsage], None],
    non_streaming_model_requests: bool,
    state: _StreamingState,
    flush_inter_call_response: Callable[[], None],
) -> PydanticAIAgentRunResult[str]:
    """Drive ``agent.iter`` so cumulative usage is captured even on cancellation.

    The supplied ``record_usage`` callback is invoked exactly once per call —
    on success, error, or cancellation — with the cumulative ``RunUsage`` for
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
    """
    async with agent.iter(
        user_prompt=prompt,
        message_history=message_history,
        usage_limits=UsageLimits(request_limit=None),
        model_settings=ModelSettings(max_tokens=max_tokens),
    ) as agent_run:
        try:
            node = agent_run.next_node
            while not isinstance(node, End):
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
        finally:
            record_usage(agent_run.usage)


class PydanticAIRunner(AgentRunner):
    """Runs a single Pydantic AI agent as an autonomous participant.

    Uses ``agent.run()`` with ``event_stream_handler`` so the agent
    executes all tool calls to completion while accumulating reasoning
    text and tool results for JSONL logging.
    """

    def __init__(self, max_turns: int, event_bus: EventBus) -> None:
        self._max_turns = max_turns
        self._event_bus = event_bus

    async def start(
        self,
        agent_config: AgentConfig,
        mcp_server_url: str,
        runtime: SimulationRuntime,
        cost_tracker: dict[str, float],
    ) -> AgentRunResult:
        """Launch a Pydantic AI agent that loops until it receives a done notification."""
        event_logger = runtime.event_logger
        agent_id = agent_config.agent_id
        provider = agent_config.provider
        logger.info(
            "Starting Pydantic AI agent %s (%s) max_turns=%d provider=%s model=%s",
            agent_id,
            agent_config.role_name,
            self._max_turns,
            provider,
            agent_config.model,
        )

        mcp_url = f"{mcp_server_url}?agent_id={agent_id}"
        mcp_toolset = MCPToolset(mcp_url)

        full_system_prompt = build_full_system_prompt(
            base_prompt=agent_config.system_prompt,
            role_name=agent_config.role_name,
        )

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
            prompt: str = CONTINUE_PROMPT
        else:
            prompt = INITIAL_PROMPT
        bus = self._event_bus
        all_background_tasks: list[asyncio.Task[None]] = []
        cycle_pricing = find_pricing(model=agent_config.model)
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
                        prompt,
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

                    cycle_succeeded = False
                    result: PydanticAIAgentRunResult[str] | None = None
                    try:
                        result = await _run_agent_call(
                            agent=agent,
                            prompt=prompt,
                            message_history=message_history,
                            event_stream_handler=_handle_events,
                            max_tokens=agent_config.max_tokens,
                            record_usage=_record_usage,
                            non_streaming_model_requests=non_streaming_model_requests,
                            state=captured_state,
                            flush_inter_call_response=_flush_inter_call_response,
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
                            # pydantic-ai (via genai-prices) includes cache tokens
                            # in input_tokens, so subtract them before applying
                            # the base input rate to avoid double-counting.
                            non_cached_input = max(
                                0,
                                total_input_tokens
                                - total_cache_read_tokens
                                - total_cache_write_tokens,
                            )
                            cumulative_cost = (
                                non_cached_input * cycle_pricing.input_per_mtok
                                + total_output_tokens * cycle_pricing.output_per_mtok
                                + total_cache_read_tokens * cycle_pricing.cache_read_per_mtok
                                + total_cache_write_tokens * cycle_pricing.cache_write_per_mtok
                            ) / 1_000_000
                            bus.publish(
                                event=AgentCostUpdated(
                                    agent_id=agent_id,
                                    cumulative_cost_usd=cumulative_cost,
                                ).model_dump(mode="json")
                            )
                            cost_tracker[agent_id] = cumulative_cost

                    if not cycle_succeeded or result is None:
                        all_background_tasks.extend(state.background_tasks)
                        total_turns += 1
                        prompt = CONTINUE_PROMPT
                        continue

                    message_history = result.all_messages()
                    total_turns += 1

                    self._log_compaction_summaries(
                        new_messages=result.new_messages(),
                        agent_id=agent_id,
                        round_number=runtime.current_round,
                        event_logger=event_logger,
                        state=state,
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

                    prompt = CONTINUE_PROMPT

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

    def _log_compaction_summaries(
        self,
        new_messages: list[ModelMessage],
        agent_id: str,
        round_number: int,
        event_logger: EventLogger,
        state: _StreamingState,
    ) -> None:
        """Log a ContextCompacted event for each CompactionPart produced this cycle.

        The full provider summary is only assembled on the completed message; the
        streaming events deliver it in per-delta fragments. Reading from
        ``result.new_messages()`` captures each summary once, whole. Anthropic
        returns readable text; OpenAI returns ``None`` (encrypted server-side).
        """
        for message in new_messages:
            if not isinstance(message, ModelResponse):
                continue
            for part in message.parts:
                if not isinstance(part, CompactionPart):
                    continue
                summary = part.content
                if isinstance(summary, str):
                    summary_char_count = len(summary)
                    summary_text = summary
                else:
                    summary_char_count = 0
                    summary_text = ""
                provider_name = part.provider_name
                if provider_name is None:
                    provider_name = "unknown"
                logger.info(
                    "Agent %s context compacted by %s: %d-char summary: %.200s",
                    agent_id,
                    provider_name,
                    summary_char_count,
                    summary_text,
                )
                state.spawn_log_task(
                    event_logger.log(
                        event=ContextCompacted(
                            agent_id=agent_id,
                            round_number=round_number,
                            provider_name=provider_name,
                            summary_char_count=summary_char_count,
                            summary_text=summary_text,
                        )
                    )
                )

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

        elif isinstance(event, PartDeltaEvent):
            if isinstance(event.delta, TextPartDelta):
                state.accumulated_text += event.delta.content_delta
            elif isinstance(event.delta, ThinkingPartDelta):
                if event.delta.content_delta:
                    state.accumulated_thinking += event.delta.content_delta

        elif isinstance(event, FunctionToolCallEvent):
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
