"""Runs a single agent within a simulation, handling its turn
loop and LLM interactions.
"""

import asyncio
import logging
from typing import Any

from schmidt.event_bus import EventBus
from schmidt.event_logger import EventLogger
from schmidt.llm.prompt_builder import PromptBuilder
from schmidt.llm.provider import LLMMessage, LLMProvider, LLMResponse
from schmidt.llm.tool_arg_extractor import SendMessageTextExtractor
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import LLMRequestSent, LLMResponseReceived, ToolCalled, ToolResultReturned
from schmidt.models.simulation_state import TurnDecision
from schmidt.models.tool_definition import ToolSpec
from schmidt.scenario_protocol import SimulationScenario
from schmidt.server.streaming_event import MessagePreview, TokenDelta
from schmidt.tools.tool_executor import ToolExecutor
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS_PER_TURN = 10


class TurnSummary:
    """Accumulates the messages sent and tools called during a single agent turn."""

    def __init__(self) -> None:
        self.messages_sent: list[str] = []
        self.tools_called: list[str] = []
        self.passed: bool = False


class AgentRunner:
    """Drives a single agent through its turn lifecycle.

    Waits for wake signals, retrieves turn decisions from the queue,
    builds prompts with channel context and injections, calls the LLM,
    and executes any tool calls returned by the LLM in a loop. Uses the
    streaming LLM API and publishes TokenDelta events to the EventBus
    for real-time token delivery.
    """

    def __init__(
        self,
        config: AgentConfig,
        llm_provider: LLMProvider,
        prompt_builder: PromptBuilder,
        scenario: SimulationScenario,
        tool_registry: ToolRegistry,
        tool_executor: ToolExecutor,
        event_logger: EventLogger,
        wake_event: asyncio.Event,
        turn_queue: asyncio.Queue[TurnDecision],
        done_event: asyncio.Event,
        event_bus: EventBus,
    ) -> None:
        self._config = config
        self._llm_provider = llm_provider
        self._prompt_builder = prompt_builder
        self._scenario = scenario
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._event_logger = event_logger
        self._wake_event = wake_event
        self._turn_queue = turn_queue
        self._done_event = done_event
        self._event_bus = event_bus
        self._last_injected_round = 0
        self.last_turn_summary: TurnSummary = TurnSummary()

    async def run(self) -> None:
        """Run the agent loop indefinitely, waiting for wake signals
        and processing one turn per signal.
        """
        logger.info("Agent %s started, waiting for turns", self._config.agent_id)
        while True:
            await self._wake_event.wait()
            self._wake_event.clear()

            decision = await self._turn_queue.get()

            logger.debug(
                "Agent %s woke for round %d",
                self._config.agent_id,
                decision.round_number,
            )
            await self._process_turn(decision=decision)

            self._done_event.set()

    async def _process_turn(self, decision: TurnDecision) -> None:
        """Execute a single turn: fetch any injection, build the
        message history, and run the LLM tool loop.
        """
        self.last_turn_summary = TurnSummary()

        injection: str | None = None
        if decision.round_number > self._last_injected_round:
            injection = self._scenario.get_injection(
                round_number=decision.round_number, agent_id=self._config.agent_id
            )
            self._last_injected_round = decision.round_number
            if injection is not None:
                logger.debug(
                    "Agent %s received injection for round %d",
                    self._config.agent_id,
                    decision.round_number,
                )

        messages = self._prompt_builder.build_messages(
            agent_id=self._config.agent_id,
            visible_channel_ids=list(self._config.channel_ids),
            injection=injection,
        )

        tools = self._tool_registry.get_specs(names=list(self._config.tool_names))
        if decision.excluded_tool_names:
            excluded = set(decision.excluded_tool_names)
            tools = [t for t in tools if t.name not in excluded]

        turn_context = (
            "It's your turn to speak. "
            "You can send messages to any channel. "
            "Call pass_turn if you have nothing to add."
        )

        # Ensure conversation ends with a user message (required by Claude API)
        if messages and messages[-1].role == "user" and isinstance(messages[-1].content, str):
            messages[-1] = LLMMessage(
                role="user",
                content=f"{messages[-1].content}\n\n{turn_context}",
            )
        else:
            messages.append(LLMMessage(role="user", content=turn_context))

        await self._llm_tool_loop(messages=messages, tools=tools, max_tokens=decision.max_tokens)

    async def _call_llm(
        self,
        messages: list[LLMMessage],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> LLMResponse:
        """Call the LLM with streaming, publishing token and message preview events."""
        agent_id = self._config.agent_id
        bus = self._event_bus
        extractors: dict[int, SendMessageTextExtractor] = {}

        async def on_token(text: str) -> None:
            delta = TokenDelta(
                agent_id=agent_id,
                text=text,
                is_final=False,
            )
            bus.publish(event=delta.model_dump(mode="json"))

        # Buffer message preview text per block and flush periodically so the
        # frontend receives events spread across multiple animation frames
        # instead of a single burst.
        preview_buffers: dict[int, str] = {}
        last_preview_time = 0.0
        preview_flush_interval = 0.03  # 30ms — roughly 2 animation frames

        def _flush_preview(block_index: int) -> None:
            nonlocal last_preview_time
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
            bus.publish(event=preview.model_dump(mode="json"))
            last_preview_time = asyncio.get_running_loop().time()

        async def on_tool_arg_delta(
            block_index: int,
            tool_name: str,
            _arg_chunk: str,
            accumulated_json: str,
        ) -> None:
            nonlocal last_preview_time
            if tool_name != "send_message":
                return
            if block_index not in extractors:
                extractors[block_index] = SendMessageTextExtractor()
            result = extractors[block_index].feed(accumulated_json=accumulated_json)
            if not result.new_text or result.channel_id is None:
                return

            preview_buffers[block_index] = preview_buffers.get(block_index, "") + result.new_text

            now = asyncio.get_running_loop().time()
            elapsed = now - last_preview_time
            if elapsed >= preview_flush_interval:
                _flush_preview(block_index=block_index)
            else:
                # Yield and flush after the interval elapses
                await asyncio.sleep(preview_flush_interval - elapsed)
                _flush_preview(block_index=block_index)

        response = await self._llm_provider.generate_streaming(
            system_prompt=self._config.system_prompt,
            messages=messages,
            tools=tools,
            force_tool_use=False,
            max_tokens=max_tokens,
            on_token=on_token,
            on_tool_arg_delta=on_tool_arg_delta,
        )

        # Flush any remaining buffered preview text
        for block_index in list(preview_buffers.keys()):
            _flush_preview(block_index=block_index)

        # Clear any active message previews before tool execution
        for extractor in extractors.values():
            channel_id = extractor.channel_id
            if channel_id is not None:
                final_preview = MessagePreview(
                    agent_id=agent_id,
                    channel_id=channel_id,
                    text="",
                    is_final=True,
                )
                bus.publish(event=final_preview.model_dump(mode="json"))

        # Signal that text streaming is complete for this LLM call
        final_delta = TokenDelta(
            agent_id=agent_id,
            text="",
            is_final=True,
        )
        bus.publish(event=final_delta.model_dump(mode="json"))

        return response

    async def _llm_tool_loop(
        self,
        messages: list[LLMMessage],
        tools: list[ToolSpec],
        max_tokens: int,
    ) -> None:
        """Call the LLM and execute returned tool calls in a loop,
        up to MAX_TOOL_CALLS_PER_TURN iterations.

        Agents can send multiple messages per turn. After pass_turn is
        called, both send_message and pass_turn are removed from available
        tools. After send_message is called, pass_turn is removed but
        send_message remains available for additional messages.
        """
        pass_turn_used = False
        has_sent_message = False

        for iteration in range(MAX_TOOL_CALLS_PER_TURN):
            active_tools = list(tools)
            if pass_turn_used:
                active_tools = [
                    t for t in active_tools if t.name not in ("send_message", "pass_turn")
                ]
            elif has_sent_message:
                active_tools = [t for t in active_tools if t.name != "pass_turn"]

            await self._event_logger.log(
                event=LLMRequestSent(
                    agent_id=self._config.agent_id,
                    system_prompt=self._config.system_prompt,
                    messages=[{"role": m.role, "content": m.content} for m in messages],
                    tool_names=[t.name for t in active_tools],
                )
            )

            response = await self._call_llm(
                messages=messages,
                tools=active_tools,
                max_tokens=max_tokens,
            )

            await self._event_logger.log(
                event=LLMResponseReceived(
                    agent_id=self._config.agent_id,
                    text=response.text,
                    tool_calls=response.tool_calls,
                    stop_reason=response.stop_reason,
                    usage=response.usage,
                )
            )

            if not response.tool_calls:
                logger.debug(
                    "Agent %s finished tool loop after %d iteration(s), stop_reason=%s",
                    self._config.agent_id,
                    iteration + 1,
                    response.stop_reason,
                )
                break

            # Append the full assistant response (with tool_use blocks) as structured content
            messages.append(LLMMessage(role="assistant", content=response.raw_content))

            # Process each tool call and collect results
            tool_results: list[dict[str, Any]] = []
            for call in response.tool_calls:
                await self._event_logger.log(
                    event=ToolCalled(
                        agent_id=self._config.agent_id,
                        request=call,
                    )
                )

                result = await self._tool_executor.execute(
                    request=call,
                    agent_id=self._config.agent_id,
                )

                await self._event_logger.log(
                    event=ToolResultReturned(
                        agent_id=self._config.agent_id,
                        result=result,
                    )
                )

                if call.tool_name == "send_message" and not result.is_error:
                    has_sent_message = True
                    channel_id = str(call.arguments.get("channel_id", ""))
                    text = str(call.arguments.get("text", ""))
                    self.last_turn_summary.messages_sent.append(f"[{channel_id}] {text[:80]}")

                if call.tool_name == "pass_turn" and not result.is_error:
                    pass_turn_used = True
                    self.last_turn_summary.passed = True

                self.last_turn_summary.tools_called.append(call.tool_name)

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.call_id,
                        "content": result.output,
                    }
                )

            # Append all tool results as a single user message with structured content
            messages.append(LLMMessage(role="user", content=tool_results))

            if pass_turn_used:
                logger.debug("Agent %s passed turn, ending tool loop", self._config.agent_id)
                break
