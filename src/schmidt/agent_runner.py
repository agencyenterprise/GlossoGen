"""Runs a single agent within a simulation, handling its turn
loop and LLM interactions.
"""

import asyncio
import logging
from typing import Any

from schmidt.event_logger import EventLogger
from schmidt.llm.prompt_builder import PromptBuilder
from schmidt.llm.provider import LLMMessage, LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import LLMRequestSent, LLMResponseReceived, ToolCalled, ToolResultReturned
from schmidt.models.simulation_state import TurnDecision
from schmidt.models.tool_definition import ToolSpec
from schmidt.scenario_protocol import SimulationScenario
from schmidt.tools.tool_executor import ToolExecutor
from schmidt.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS_PER_TURN = 10


class TurnSummary:
    """Accumulates the messages sent and tools called during a single agent turn."""

    def __init__(self) -> None:
        self.messages_sent: list[str] = []
        self.tools_called: list[str] = []


class AgentRunner:
    """Drives a single agent through its turn lifecycle.

    Waits for wake signals, retrieves turn decisions from the queue,
    builds prompts with channel context and injections, calls the LLM,
    and executes any tool calls returned by the LLM in a loop.
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
                "Agent %s woke for round %d on channel %s",
                self._config.agent_id,
                decision.round_number,
                decision.channel_id,
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

        target_channel_id = decision.channel_id
        visible_channel_ids = list(self._config.channel_ids)

        messages = self._prompt_builder.build_messages(
            agent_id=self._config.agent_id,
            visible_channel_ids=visible_channel_ids,
            injection=injection,
        )

        tools = self._tool_registry.get_specs(names=list(self._config.tool_names))

        # Add turn context
        target_display = self._scenario.get_channel_display_name(
            channel_id=target_channel_id, agent_id=self._config.agent_id
        )
        turn_context = (
            f'It\'s your turn to contribute to the "{target_display}" channel. '
            f"Send one focused message to channel_id: {target_channel_id}"
        )

        if not messages or messages[0].role != "user":
            messages.insert(0, LLMMessage(role="user", content=turn_context))
        elif isinstance(messages[-1].content, str) and messages[-1].role == "user":
            messages[-1] = LLMMessage(
                role="user",
                content=f"{messages[-1].content}\n\n{turn_context}",
            )
        else:
            messages.append(LLMMessage(role="user", content=turn_context))

        await self._llm_tool_loop(messages=messages, tools=tools)

    async def _llm_tool_loop(
        self,
        messages: list[LLMMessage],
        tools: list[ToolSpec],
    ) -> None:
        """Call the LLM and execute returned tool calls in a loop,
        up to MAX_TOOL_CALLS_PER_TURN iterations.

        Removes the send_message tool from subsequent iterations
        after it has been used once.
        """
        send_message_used = False

        for iteration in range(MAX_TOOL_CALLS_PER_TURN):
            # Remove send_message from tools after first use
            active_tools = tools
            if send_message_used:
                active_tools = [t for t in tools if t.name != "send_message"]

            await self._event_logger.log(
                event=LLMRequestSent(
                    agent_id=self._config.agent_id,
                    system_prompt=self._config.system_prompt,
                    messages=[{"role": m.role, "content": m.content} for m in messages],
                    tool_names=[t.name for t in active_tools],
                )
            )

            response = await self._llm_provider.generate(
                system_prompt=self._config.system_prompt,
                messages=messages,
                tools=active_tools,
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
                    send_message_used = True
                    channel_id = str(call.arguments.get("channel_id", ""))
                    text = str(call.arguments.get("text", ""))
                    self.last_turn_summary.messages_sent.append(f"[{channel_id}] {text[:80]}")

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
