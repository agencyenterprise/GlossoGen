"""Claude Code agent runner using the Claude Agent SDK.

Launches a Claude Code instance that connects to the simulation runtime's
MCP server and participates autonomously in the scenario. Each cycle, the
agent calls check_messages, acts on the result, and is re-prompted to
continue the loop.
"""

import logging

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    UserMessage,
    query,
)
from claude_agent_sdk.types import McpHttpServerConfig, TextBlock, ThinkingBlock, ToolUseBlock

from schmidt.event_logger import EventLogger
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import LLMResponseReceived, TokenUsage
from schmidt.models.tool_definition import ToolCallRequest
from schmidt.runners.agent_runner_base import AgentRunner

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_SUFFIX = (
    "\n\n---\n"
    "COMMUNICATION PROTOCOL:\n"
    "You are in a live team session. Follow this exact protocol:\n"
    "1. Call check_messages() to receive events\n"
    "2. When you receive new_info or new_messages, call list_channels() to see your channels, "
    "then call send_message(channel_id, text) to share your thoughts with the team\n"
    "3. Call check_messages() again\n"
    "4. Repeat until check_messages returns type=done\n\n"
    "RULES:\n"
    "- Text you write outside of send_message() is NOT visible to anyone\n"
    "- You MUST use send_message() to communicate — there is no other way\n"
    "- NEVER stop or end your turn without calling check_messages() first\n"
    "- After receiving information, ALWAYS call send_message() "
    "before calling check_messages() again"
)

INITIAL_PROMPT = "Start by calling check_messages() to see if there is anything new."

CONTINUE_PROMPT = (
    "Call check_messages() to wait for the next event. "
    "When you get new info, use send_message() to share your response with the team."
)

BASE_MCP_TOOLS = [
    "mcp__comms__check_messages",
    "mcp__comms__read_channel",
    "mcp__comms__send_message",
    "mcp__comms__list_channels",
    "mcp__comms__get_channel_members",
]


class ClaudeCodeRunner(AgentRunner):
    """Runs a single Claude Code instance as an autonomous agent via the Agent SDK.

    Uses a loop of ``query()`` calls with ``continue_conversation=True`` to
    keep the agent in a persistent check_messages loop. Each iteration
    re-prompts the agent to call check_messages again.
    """

    def __init__(self, max_turns: int) -> None:
        self._max_turns = max_turns

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

                got_done = False
                async for message in query(
                    prompt=prompt,
                    options=options,
                ):
                    if isinstance(message, ResultMessage):
                        session_id = message.session_id
                        total_cost += message.total_cost_usd or 0.0
                        total_turns += message.num_turns
                        logger.info(
                            "Agent %s cycle result: session=%s, turns=%d, stop=%s, cost=$%.4f",
                            agent_config.agent_id,
                            session_id,
                            message.num_turns,
                            message.stop_reason,
                            message.total_cost_usd,
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
                                    agent_config.agent_id,
                                    block.name,
                                    block.input,
                                )
                        if text_parts:
                            joined_text = "\n".join(text_parts)
                            logger.info(
                                "Agent %s reasoning: %.200s",
                                agent_config.agent_id,
                                joined_text,
                            )
                            await event_logger.log(
                                LLMResponseReceived(
                                    agent_id=agent_config.agent_id,
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
                            agent_config.agent_id,
                            content,
                        )
                        if "'done'" in content or '"done"' in content:
                            got_done = True
                    elif isinstance(message, SystemMessage):
                        logger.debug(
                            "Agent %s system message: subtype=%s data=%s",
                            agent_config.agent_id,
                            message.subtype,
                            message.data,
                        )
                    else:
                        logger.debug(
                            "Agent %s activity: %s",
                            agent_config.agent_id,
                            type(message).__name__,
                        )

                if got_done:
                    logger.info(
                        "Agent %s received done notification, stopping",
                        agent_config.agent_id,
                    )
                    break

                prompt = CONTINUE_PROMPT
        except Exception:
            logger.exception("Agent %s SDK query failed", agent_config.agent_id)
            raise

        logger.info(
            "Agent %s finished. Total turns: %d, total cost: $%.4f",
            agent_config.agent_id,
            total_turns,
            total_cost,
        )
