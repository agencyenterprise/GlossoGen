"""Claude Code agent runner using the Claude Agent SDK.

Launches a Claude Code instance that connects to the simulation runtime's
MCP server and participates autonomously in the scenario. Each cycle, the
agent calls check_messages, acts on the result, and is re-prompted to
continue the loop. Publishes token-level streaming events to the EventBus
for real-time frontend display.
"""

import asyncio
import logging
from typing import Any

from claude_agent_sdk import (  # pyright: ignore[reportMissingImports]
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    UserMessage,
    query,
)
from claude_agent_sdk.types import (  # pyright: ignore[reportMissingImports]
    McpHttpServerConfig,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)

from schmidt.event_bus import EventBus
from schmidt.event_logger import EventLogger
from schmidt.llm.tool_arg_extractor import SendMessageTextExtractor
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import LLMResponseReceived, TokenUsage
from schmidt.models.tool_definition import ToolCallRequest
from schmidt.runners.agent_runner_base import AgentRunner
from schmidt.server.streaming_event import MessagePreview, TokenDelta

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_SUFFIX = (
    "\n\n---\n"
    "COMMUNICATION PROTOCOL:\n"
    "You are in a live team session. Other participants can send messages at any time, "
    "even while you are composing yours.\n\n"
    "Follow this exact protocol:\n"
    "1. Call check_messages() to receive events\n"
    "2. When you receive new_info or new_messages, call read_channel(channel_id, last_n) "
    "to see the messages\n"
    "3. Call send_message(channel_id, text, force) to reply. Set force=false\n"
    "4. If send_message returns status='conflict', new messages arrived while you were "
    "composing your reply. The response includes those messages. Read them, then decide:\n"
    "   - Revise your message and call send_message again with force=false\n"
    "   - If your original message is still relevant, re-send it with force=true\n"
    "5. Call check_messages() again and repeat until it returns type=done\n\n"
    "RULES:\n"
    "- Text you write outside of send_message() is NOT visible to anyone\n"
    "- You MUST use send_message() to communicate — there is no other way\n"
    "- NEVER stop or end your turn without calling check_messages() first\n"
    "- After receiving information, ALWAYS call send_message() "
    "before calling check_messages() again\n"
    "- When you get a conflict on send_message, ALWAYS review the new messages "
    "before deciding whether to revise or force-send"
)

INITIAL_PROMPT = "Start by calling check_messages() to see if there is anything new."

CONTINUE_PROMPT = (
    "Call check_messages() to wait for the next event. "
    "When you get new info, read the channel and use send_message(channel_id, text, force=false) "
    "to share your response with the team."
)

BASE_MCP_TOOLS = [
    "mcp__comms__check_messages",
    "mcp__comms__read_channel",
    "mcp__comms__send_message",
    "mcp__comms__list_channels",
    "mcp__comms__get_channel_members",
]

PREVIEW_FLUSH_INTERVAL = 0.03  # 30ms — roughly 2 animation frames


class ClaudeCodeRunner(AgentRunner):
    """Runs a single Claude Code instance as an autonomous agent via the Agent SDK.

    Uses a loop of ``query()`` calls with ``continue_conversation=True`` to
    keep the agent in a persistent check_messages loop. Each iteration
    re-prompts the agent to call check_messages again. Publishes ``TokenDelta``
    and ``MessagePreview`` events to the EventBus for real-time streaming.
    """

    def __init__(self, max_turns: int, event_bus: EventBus) -> None:
        self._max_turns = max_turns
        self._event_bus = event_bus

    async def start(
        self,
        agent_config: AgentConfig,
        mcp_server_url: str,
        event_logger: EventLogger,
    ) -> None:
        """Launch a Claude Code agent that loops until it receives a done notification."""
        logger.info(
            "Starting Claude Code agent %s (%s) max_turns=%d",
            agent_config.agent_id,
            agent_config.role_name,
            self._max_turns,
        )

        server_config: McpHttpServerConfig = {
            "type": "http",
            "url": f"{mcp_server_url}?agent_id={agent_config.agent_id}",
        }

        # Base MCP tools + scenario-specific tools from agent config.
        allowed_tools = list(BASE_MCP_TOOLS)
        for tool_name in agent_config.tool_names:
            prefixed = f"mcp__comms__{tool_name}"
            if prefixed not in allowed_tools:
                allowed_tools.append(prefixed)
        logger.debug("Agent %s allowed tools: %s", agent_config.agent_id, allowed_tools)

        full_system_prompt = agent_config.system_prompt + SYSTEM_PROMPT_SUFFIX

        base_options = ClaudeAgentOptions(
            system_prompt=full_system_prompt,
            model=agent_config.model,
            mcp_servers={"comms": server_config},
            tools=["ToolSearch"],
            allowed_tools=allowed_tools,
            setting_sources=[],
            max_turns=self._max_turns,
        )

        prompt = INITIAL_PROMPT
        session_id: str | None = None
        total_cost = 0.0
        total_turns = 0
        agent_id = agent_config.agent_id
        bus = self._event_bus

        try:
            while True:
                if session_id is None:
                    options = base_options
                else:
                    options = ClaudeAgentOptions(
                        system_prompt=full_system_prompt,
                        model=agent_config.model,
                        mcp_servers={"comms": server_config},
                        tools=["ToolSearch"],
                        allowed_tools=allowed_tools,
                        setting_sources=[],
                        max_turns=self._max_turns,
                        resume=session_id,
                    )

                # Track tool_use blocks for message preview extraction
                tool_use_builders: dict[int, dict[str, Any]] = {}
                extractors: dict[int, SendMessageTextExtractor] = {}
                preview_buffers: dict[int, str] = {}
                last_preview_time = 0.0

                got_done = False
                async for message in query(
                    prompt=prompt,
                    options=options,
                ):
                    if isinstance(message, StreamEvent):
                        self._handle_stream_event(
                            agent_id=agent_id,
                            stream_event=message,
                            tool_use_builders=tool_use_builders,
                            extractors=extractors,
                            preview_buffers=preview_buffers,
                            last_preview_time=last_preview_time,
                        )
                    elif isinstance(message, ResultMessage):
                        session_id = message.session_id
                        total_cost += message.total_cost_usd or 0.0
                        total_turns += message.num_turns
                        logger.info(
                            "Agent %s cycle result: session=%s, turns=%d, stop=%s, cost=$%.4f",
                            agent_id,
                            session_id,
                            message.num_turns,
                            message.stop_reason,
                            message.total_cost_usd,
                        )
                        # Clear streaming state at end of cycle
                        self._flush_all_previews(
                            agent_id=agent_id,
                            extractors=extractors,
                            preview_buffers=preview_buffers,
                        )
                        bus.publish(
                            event=TokenDelta(
                                agent_id=agent_id,
                                text="",
                                is_final=True,
                            ).model_dump(mode="json")
                        )
                    elif isinstance(message, AssistantMessage):
                        text_parts: list[str] = []
                        tool_calls: list[ToolCallRequest] = []
                        for block in message.content:
                            if isinstance(block, ThinkingBlock):
                                text_parts.append(block.thinking)
                            elif isinstance(block, TextBlock):
                                text_parts.append(block.text)
                            elif isinstance(block, ToolUseBlock):
                                tool_calls.append(
                                    ToolCallRequest(
                                        call_id=block.id,
                                        tool_name=block.name,
                                        arguments=block.input,
                                    )
                                )
                                logger.info(
                                    "Agent %s tool call: %s(%s)",
                                    agent_id,
                                    block.name,
                                    block.input,
                                )
                        if text_parts:
                            joined_text = "\n".join(text_parts)
                            logger.info(
                                "Agent %s reasoning: %.200s",
                                agent_id,
                                joined_text,
                            )
                            await event_logger.log(
                                LLMResponseReceived(
                                    agent_id=agent_id,
                                    text=joined_text,
                                    tool_calls=tool_calls,
                                    stop_reason="end_turn",
                                    usage=TokenUsage(
                                        input_tokens=0,
                                        output_tokens=0,
                                        cache_read_input_tokens=0,
                                        cache_creation_input_tokens=0,
                                    ),
                                )
                            )
                    elif isinstance(message, UserMessage):
                        content = str(message.content)
                        logger.info(
                            "Agent %s user message: %.200s",
                            agent_id,
                            content,
                        )
                        if "'done'" in content or '"done"' in content:
                            got_done = True
                    elif isinstance(message, SystemMessage):
                        logger.debug(
                            "Agent %s system message: subtype=%s data=%s",
                            agent_id,
                            message.subtype,
                            message.data,
                        )
                    else:
                        logger.debug(
                            "Agent %s activity: %s",
                            agent_id,
                            type(message).__name__,
                        )

                if got_done:
                    logger.info(
                        "Agent %s received done notification, stopping",
                        agent_id,
                    )
                    break

                prompt = CONTINUE_PROMPT
        except Exception:
            logger.exception("Agent %s SDK query failed", agent_id)
            raise

        logger.info(
            "Agent %s finished. Total turns: %d, total cost: $%.4f",
            agent_id,
            total_turns,
            total_cost,
        )

    def _handle_stream_event(
        self,
        agent_id: str,
        stream_event: StreamEvent,
        tool_use_builders: dict[int, dict[str, Any]],
        extractors: dict[int, SendMessageTextExtractor],
        preview_buffers: dict[int, str],
        last_preview_time: float,
    ) -> None:
        """Process a raw Anthropic API streaming event for token and message preview delivery."""
        event = stream_event.event
        event_type = event.get("type", "")

        if event_type == "content_block_start":
            block = event.get("content_block", {})
            index = event.get("index", 0)
            if block.get("type") == "tool_use":
                tool_use_builders[index] = {
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "input_json": "",
                }

        elif event_type == "content_block_delta":
            index = event.get("index", 0)
            delta = event.get("delta", {})
            delta_type = delta.get("type", "")

            if delta_type == "text_delta":
                text = delta.get("text", "")
                if text:
                    token = TokenDelta(
                        agent_id=agent_id,
                        text=text,
                        is_final=False,
                    )
                    self._event_bus.publish(event=token.model_dump(mode="json"))

            elif delta_type == "input_json_delta":
                builder = tool_use_builders.get(index)
                if builder is not None:
                    partial_json = delta.get("partial_json", "")
                    builder["input_json"] += partial_json

                    if builder["name"] == "mcp__comms__send_message":
                        if index not in extractors:
                            extractors[index] = SendMessageTextExtractor()
                        result = extractors[index].feed(
                            accumulated_json=builder["input_json"],
                        )
                        if result.new_text and result.channel_id is not None:
                            preview_buffers[index] = (
                                preview_buffers.get(index, "") + result.new_text
                            )
                            now = asyncio.get_event_loop().time()
                            elapsed = now - last_preview_time
                            if elapsed >= PREVIEW_FLUSH_INTERVAL:
                                self._flush_preview(
                                    agent_id=agent_id,
                                    block_index=index,
                                    extractors=extractors,
                                    preview_buffers=preview_buffers,
                                )

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
