"""Builds pydantic-ai ModelMessage history from simulation JSONL events.

Reconstructs the multi-turn conversation an agent experienced during a
simulation, producing a list of ``ModelMessage`` objects suitable for
passing as ``message_history`` to ``agent.run()`` on resume. Includes
thinking parts, text parts, tool calls, and tool results in the same
structure pydantic-ai produces during a live run.
"""

import logging
from datetime import datetime

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from schmidt.models.event import LLMResponseReceived, SimulationEvent, ToolResultReceived
from schmidt.models.tool_definition import ToolCallRequest
from schmidt.runners.communication_protocol import CONTINUE_PROMPT, INITIAL_PROMPT

logger = logging.getLogger(__name__)


CHANNEL_SCOPED_TOOLS: frozenset[str] = frozenset({"send_message", "read_channel"})


def _tool_call_targets_blocked_channel(
    tool_call: ToolCallRequest,
    blocked_channel_ids: frozenset[str],
) -> bool:
    """Return True when the tool call targets a channel in the blocked set."""
    if tool_call.tool_name not in CHANNEL_SCOPED_TOOLS:
        return False
    channel_id = tool_call.arguments.get("channel_id")
    return isinstance(channel_id, str) and channel_id in blocked_channel_ids


def build_message_history(
    events: list[SimulationEvent],
    agent_id: str,
    system_prompt: str,
    target_timestamp: datetime,
    tool_calls_only: bool,
    blocked_channel_ids: frozenset[str],
) -> list[ModelMessage]:
    """Build a pydantic-ai message history for an agent from JSONL events.

    Walks events chronologically up to ``target_timestamp``, extracting
    LLM responses and tool results for the specified agent. Produces
    alternating ``ModelRequest`` / ``ModelResponse`` messages matching
    the structure pydantic-ai creates during a live run.

    When ``tool_calls_only`` is True, ``TextPart`` and ``ThinkingPart``
    are stripped from each ``ModelResponse``; only ``ToolCallPart``
    instances survive. When ``blocked_channel_ids`` is non-empty, every
    ``send_message`` and ``read_channel`` call targeting one of those
    channels is dropped along with its matching tool return — used by
    the replace-agent flow to hide e.g. postmortem traffic from the
    new agent while exposing the rest of the prior tool history.
    """
    llm_responses: list[LLMResponseReceived] = []
    tool_results_by_call_id: dict[str, ToolResultReceived] = {}

    for event in events:
        if event.timestamp > target_timestamp:
            break
        if isinstance(event, LLMResponseReceived) and event.agent_id == agent_id:
            llm_responses.append(event)
        elif isinstance(event, ToolResultReceived) and event.agent_id == agent_id:
            tool_results_by_call_id[event.call_id] = event

    if not llm_responses:
        return []

    messages: list[ModelMessage] = [
        ModelRequest(
            parts=[
                SystemPromptPart(content=system_prompt),
                UserPromptPart(content=INITIAL_PROMPT),
            ],
        )
    ]

    for llm_resp in llm_responses:
        kept_tool_calls = [
            tc
            for tc in llm_resp.tool_calls
            if not _tool_call_targets_blocked_channel(
                tool_call=tc,
                blocked_channel_ids=blocked_channel_ids,
            )
        ]

        response_parts: list[ThinkingPart | TextPart | ToolCallPart] = []

        if not tool_calls_only:
            thinking = getattr(llm_resp, "thinking", None)
            if thinking:
                response_parts.append(ThinkingPart(content=thinking))

            if llm_resp.text:
                response_parts.append(TextPart(content=llm_resp.text))

        for tc in kept_tool_calls:
            response_parts.append(
                ToolCallPart(
                    tool_name=tc.tool_name,
                    args=tc.arguments,
                    tool_call_id=tc.call_id,
                )
            )

        cycle_kept = bool(response_parts)
        if cycle_kept:
            messages.append(
                ModelResponse(
                    parts=response_parts,
                    timestamp=llm_resp.timestamp,
                )
            )

        tool_return_parts: list[ToolReturnPart] = []
        for tc in kept_tool_calls:
            result_event = tool_results_by_call_id.get(tc.call_id)
            if result_event is not None:
                tool_return_parts.append(
                    ToolReturnPart(
                        tool_name=result_event.tool_name,
                        content=result_event.result,
                        tool_call_id=result_event.call_id,
                        timestamp=result_event.timestamp,
                    )
                )

        if tool_return_parts:
            messages.append(ModelRequest(parts=tool_return_parts))

        if cycle_kept and llm_resp.stop_reason == "end_turn" and llm_resp is not llm_responses[-1]:
            messages.append(
                ModelRequest(
                    parts=[UserPromptPart(content=CONTINUE_PROMPT)],
                )
            )

    return messages
