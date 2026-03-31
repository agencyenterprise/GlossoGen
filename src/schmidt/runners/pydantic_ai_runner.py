"""Pydantic AI agent runner using the pydantic-ai framework.

Launches a Pydantic AI agent that connects to the simulation runtime's
MCP server and participates autonomously in the scenario. Uses
``agent.run()`` with an ``event_stream_handler`` for real-time token
streaming while running tool calls to completion.
"""

import asyncio
import logging
from collections.abc import AsyncIterable

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage, UsageLimits

from schmidt.event_bus import EventBus
from schmidt.event_logger import EventLogger
from schmidt.llm.tool_arg_extractor import SendMessageTextExtractor
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import LLMResponseReceived, TokenUsage, ToolResultReceived
from schmidt.models.tool_definition import ToolCallRequest
from schmidt.runners.agent_run_result import AgentRunResult
from schmidt.runners.agent_runner_base import AgentRunner
from schmidt.runners.communication_protocol import (
    CONTINUE_PROMPT,
    INITIAL_PROMPT,
    PREVIEW_FLUSH_INTERVAL,
    build_full_system_prompt,
)
from schmidt.runtime.mcp_tools import HIDDEN_TOOL_NAMES
from schmidt.server.streaming_event import AgentCostUpdated, MessagePreview, TokenDelta
from schmidt.token_pricing import find_pricing

logger = logging.getLogger(__name__)


def _log_task_exception(task: asyncio.Task[None]) -> None:
    """Log exceptions from fire-and-forget event logging tasks."""
    if not task.cancelled() and task.exception() is not None:
        logger.error("Background log task failed", exc_info=task.exception())


class _StreamingState:
    """Mutable state shared between the event handler and the outer run loop."""

    def __init__(self) -> None:
        self.got_done = False
        self.extractors: dict[int, SendMessageTextExtractor] = {}
        self.accumulated_args: dict[int, str] = {}
        self.preview_buffers: dict[int, str] = {}
        self.current_tool_names: dict[int, str] = {}
        self.pending_tool_calls: dict[str, ToolCallRequest] = {}
        self.last_preview_time = 0.0
        self.accumulated_reasoning = ""
        self.accumulated_tool_calls: list[ToolCallRequest] = []


class PydanticAIRunner(AgentRunner):
    """Runs a single Pydantic AI agent as an autonomous participant.

    Uses ``agent.run()`` with ``event_stream_handler`` so the agent
    executes all tool calls to completion while streaming token deltas
    and message previews to the EventBus.
    """

    def __init__(self, max_turns: int, event_bus: EventBus, provider: str) -> None:
        self._max_turns = max_turns
        self._event_bus = event_bus
        self._provider = provider

    async def start(
        self,
        agent_config: AgentConfig,
        mcp_server_url: str,
        event_logger: EventLogger,
    ) -> AgentRunResult:
        """Launch a Pydantic AI agent that loops until it receives a done notification."""
        agent_id = agent_config.agent_id
        logger.info(
            "Starting Pydantic AI agent %s (%s) max_turns=%d",
            agent_id,
            agent_config.role_name,
            self._max_turns,
        )

        mcp_url = f"{mcp_server_url}?agent_id={agent_id}"
        mcp_server = MCPServerStreamableHTTP(mcp_url)

        full_system_prompt = build_full_system_prompt(
            base_prompt=agent_config.system_prompt,
            role_name=agent_config.role_name,
        )

        agent: Agent[None, str] = Agent(
            model=f"{self._provider}:{agent_config.model}",
            system_prompt=full_system_prompt,
            toolsets=[mcp_server],
        )

        message_history: list[ModelMessage] | None = None
        total_input_tokens = 0
        total_output_tokens = 0
        total_cache_read_tokens = 0
        total_cache_write_tokens = 0
        total_turns = 0
        prompt: str = INITIAL_PROMPT
        bus = self._event_bus

        try:
            while total_turns < self._max_turns:
                state = _StreamingState()

                async def _handle_events(
                    _ctx: RunContext[None],  # pyright: ignore[reportUnusedParameter]
                    event_stream: AsyncIterable[AgentStreamEvent],
                ) -> None:
                    async for event in event_stream:
                        self._process_stream_event(
                            agent_id=agent_id,
                            event=event,
                            state=state,
                            event_logger=event_logger,
                        )

                try:
                    result = await agent.run(
                        user_prompt=prompt,
                        message_history=message_history,
                        event_stream_handler=_handle_events,
                        usage_limits=UsageLimits(request_limit=None),
                        model_settings={"max_tokens": 16384},
                    )
                except Exception:
                    logger.exception(
                        "Agent %s run cycle failed, retrying",
                        agent_id,
                    )
                    self._flush_all_previews(
                        agent_id=agent_id,
                        extractors=state.extractors,
                        preview_buffers=state.preview_buffers,
                    )
                    bus.publish(
                        event=TokenDelta(
                            agent_id=agent_id,
                            text="",
                            is_final=True,
                        ).model_dump(mode="json")
                    )
                    total_turns += 1
                    prompt = CONTINUE_PROMPT
                    continue

                message_history = result.all_messages()
                total_turns += 1

                usage: RunUsage = result.usage()
                total_input_tokens += usage.input_tokens
                total_output_tokens += usage.output_tokens
                total_cache_read_tokens += usage.cache_read_tokens
                total_cache_write_tokens += usage.cache_write_tokens

                logger.info(
                    "Agent %s cycle %d: input=%d output=%d tokens",
                    agent_id,
                    total_turns,
                    usage.input_tokens,
                    usage.output_tokens,
                )

                cycle_pricing = find_pricing(model=agent_config.model)
                if cycle_pricing is not None:
                    cumulative_cost = (
                        total_input_tokens * cycle_pricing.input_per_mtok
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

                # Log any remaining reasoning + tool calls from the final response
                self._flush_response_block(
                    agent_id=agent_id,
                    state=state,
                    event_logger=event_logger,
                    stop_reason="end_turn",
                    usage=TokenUsage(
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cache_read_input_tokens=usage.cache_read_tokens,
                        cache_creation_input_tokens=usage.cache_write_tokens,
                    ),
                )

                # Flush streaming state
                self._flush_all_previews(
                    agent_id=agent_id,
                    extractors=state.extractors,
                    preview_buffers=state.preview_buffers,
                )

                if state.got_done:
                    logger.info(
                        "Agent %s received done notification, stopping",
                        agent_id,
                    )
                    break

                prompt = CONTINUE_PROMPT
        except Exception:
            logger.exception("Agent %s Pydantic AI run failed", agent_id)
            raise

        pricing = find_pricing(model=agent_config.model)
        if pricing is None:
            logger.warning(
                "No pricing data for model '%s', reporting zero cost",
                agent_config.model,
            )
            total_cost = 0.0
        else:
            total_cost = (
                total_input_tokens * pricing.input_per_mtok
                + total_output_tokens * pricing.output_per_mtok
                + total_cache_read_tokens * pricing.cache_read_per_mtok
                + total_cache_write_tokens * pricing.cache_write_per_mtok
            ) / 1_000_000

        logger.info(
            "Agent %s finished. Total turns: %d, total cost: $%.4f",
            agent_id,
            total_turns,
            total_cost,
        )

        return AgentRunResult(
            agent_id=agent_id,
            total_cost_usd=total_cost,
            total_turns=total_turns,
        )

    def _flush_response_block(
        self,
        agent_id: str,
        state: _StreamingState,
        event_logger: EventLogger,
        stop_reason: str,
        usage: TokenUsage | None = None,
    ) -> None:
        """Log accumulated reasoning + tool calls as one LLMResponseReceived event.

        Sends ``is_final`` to clear the frontend partial, then logs the
        committed block so the FE can display it immediately.
        """
        text = state.accumulated_reasoning.strip()
        tool_calls = list(state.accumulated_tool_calls)
        if not text and not tool_calls:
            return
        if usage is None:
            usage = TokenUsage(
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            )
        self._event_bus.publish(
            event=TokenDelta(
                agent_id=agent_id,
                text="",
                is_final=True,
            ).model_dump(mode="json")
        )
        task = asyncio.get_running_loop().create_task(
            event_logger.log(
                LLMResponseReceived(
                    agent_id=agent_id,
                    text=state.accumulated_reasoning,
                    tool_calls=tool_calls,
                    stop_reason=stop_reason,
                    usage=usage,
                )
            )
        )
        task.add_done_callback(_log_task_exception)
        state.accumulated_reasoning = ""
        state.accumulated_tool_calls = []

    def _process_stream_event(
        self,
        agent_id: str,
        event: AgentStreamEvent,
        state: _StreamingState,
        event_logger: EventLogger,
    ) -> None:
        """Route a single streaming event to the appropriate handler."""
        if isinstance(event, PartStartEvent):
            if isinstance(event.part, ToolCallPart):
                state.current_tool_names[event.index] = event.part.tool_name
                state.accumulated_args.pop(event.index, None)
            elif isinstance(event.part, (TextPart, ThinkingPart)):
                # A new text/thinking part is starting. If we have accumulated
                # tool calls from a previous response, flush them now so each
                # model response is logged as one reasoning+tools block.
                if state.accumulated_tool_calls:
                    self._flush_response_block(
                        agent_id=agent_id,
                        state=state,
                        event_logger=event_logger,
                        stop_reason="tool_use",
                    )
                if event.part.content:
                    state.accumulated_reasoning += event.part.content
                    self._event_bus.publish(
                        event=TokenDelta(
                            agent_id=agent_id,
                            text=event.part.content,
                            is_final=False,
                        ).model_dump(mode="json")
                    )

        elif isinstance(event, PartDeltaEvent):
            if isinstance(event.delta, TextPartDelta):
                state.accumulated_reasoning += event.delta.content_delta
                self._event_bus.publish(
                    event=TokenDelta(
                        agent_id=agent_id,
                        text=event.delta.content_delta,
                        is_final=False,
                    ).model_dump(mode="json")
                )
            elif isinstance(event.delta, ThinkingPartDelta):
                if event.delta.content_delta:
                    state.accumulated_reasoning += event.delta.content_delta
                    self._event_bus.publish(
                        event=TokenDelta(
                            agent_id=agent_id,
                            text=event.delta.content_delta,
                            is_final=False,
                        ).model_dump(mode="json")
                    )
            elif isinstance(event.delta, ToolCallPartDelta):
                delta_str = event.delta.args_delta
                if isinstance(delta_str, str):
                    self._handle_tool_call_delta(
                        agent_id=agent_id,
                        index=event.index,
                        args_delta=delta_str,
                        state=state,
                    )

        elif isinstance(event, FunctionToolCallEvent):
            self._flush_all_previews(
                agent_id=agent_id,
                extractors=state.extractors,
                preview_buffers=state.preview_buffers,
            )

            args = event.part.args
            if not isinstance(args, dict):
                args = {}
            tc_req = ToolCallRequest(
                call_id=event.part.tool_call_id,
                tool_name=event.part.tool_name,
                arguments=args,
            )
            state.accumulated_tool_calls.append(tc_req)
            state.pending_tool_calls[event.part.tool_call_id] = tc_req
            logger.info(
                "Agent %s tool call: %s(%s)",
                agent_id,
                event.part.tool_name,
                event.part.args,
            )

        elif isinstance(event, FunctionToolResultEvent):
            result_content = str(event.result.content)
            matched = state.pending_tool_calls.pop(event.result.tool_call_id, None)
            if matched is not None:
                if not matched.tool_name.endswith(tuple(HIDDEN_TOOL_NAMES)):
                    task = asyncio.get_running_loop().create_task(
                        event_logger.log(
                            ToolResultReceived(
                                agent_id=agent_id,
                                tool_name=matched.tool_name,
                                call_id=matched.call_id,
                                arguments=matched.arguments,
                                result=result_content,
                            )
                        )
                    )
                    task.add_done_callback(_log_task_exception)
            if matched is not None and matched.tool_name.endswith("check_messages"):
                if '"type": "done"' in result_content or "'type': 'done'" in result_content:
                    state.got_done = True

    def _handle_tool_call_delta(
        self,
        agent_id: str,
        index: int,
        args_delta: str,
        state: _StreamingState,
    ) -> None:
        """Accumulate streaming tool call arguments and emit message previews."""
        tool_name = state.current_tool_names.get(index, "")
        if "send_message" not in tool_name:
            return

        state.accumulated_args[index] = state.accumulated_args.get(index, "") + args_delta

        if index not in state.extractors:
            state.extractors[index] = SendMessageTextExtractor()

        extract_result = state.extractors[index].feed(
            accumulated_json=state.accumulated_args[index],
        )
        if extract_result.new_text and extract_result.channel_id is not None:
            state.preview_buffers[index] = (
                state.preview_buffers.get(index, "") + extract_result.new_text
            )
            now = asyncio.get_running_loop().time()
            if now - state.last_preview_time >= PREVIEW_FLUSH_INTERVAL:
                self._flush_preview(
                    agent_id=agent_id,
                    block_index=index,
                    extractors=state.extractors,
                    preview_buffers=state.preview_buffers,
                )
                state.last_preview_time = now

    def _flush_preview(
        self,
        agent_id: str,
        block_index: int,
        extractors: dict[int, SendMessageTextExtractor],
        preview_buffers: dict[int, str],
    ) -> None:
        """Flush buffered message preview text for a single tool_use block."""
        text = preview_buffers.pop(block_index, "")
        if not text:
            return
        extractor = extractors.get(block_index)
        if extractor is None:
            return
        channel_id = extractor.channel_id
        if channel_id is None:
            return
        preview = MessagePreview(
            agent_id=agent_id,
            channel_id=channel_id,
            text=text,
            is_final=False,
        )
        self._event_bus.publish(event=preview.model_dump(mode="json"))

    def _flush_all_previews(
        self,
        agent_id: str,
        extractors: dict[int, SendMessageTextExtractor],
        preview_buffers: dict[int, str],
    ) -> None:
        """Flush remaining preview text and send is_final for all active previews."""
        for block_index in list(preview_buffers.keys()):
            self._flush_preview(
                agent_id=agent_id,
                block_index=block_index,
                extractors=extractors,
                preview_buffers=preview_buffers,
            )
        for extractor in extractors.values():
            channel_id = extractor.channel_id
            if channel_id is not None:
                final = MessagePreview(
                    agent_id=agent_id,
                    channel_id=channel_id,
                    text="",
                    is_final=True,
                )
                self._event_bus.publish(event=final.model_dump(mode="json"))
        extractors.clear()
