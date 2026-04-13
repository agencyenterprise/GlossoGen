"""Builds formatted transcripts from simulation events for use by evaluators.

Extracts messages and tool calls from the event log and formats them into
human-readable transcripts labeled with sender and channel/tool context.
"""

import logging
from typing import Any

from schmidt.models.event import LLMResponseReceived, MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)

# Tool calls that produce their own MessageSent events — including them
# in the transcript would duplicate information.
_MESSAGE_TOOLS = {
    "send_message",
    "read_notifications",
    "read_channel",
    "list_channels",
    "get_channel_members",
}


def _format_tool_args(arguments: dict[str, Any]) -> str:
    """Format tool call arguments as a comma-separated key=value string."""
    return ", ".join(f"{k}={v}" for k, v in arguments.items())


def build_channel_transcript(
    events: list[SimulationEvent],
    channel_id: str,
    scenario: SimulationScenario,
) -> str:
    """Build a chronological transcript of messages on a specific channel,
    labeled with sender names.
    """
    lines: list[str] = []
    for event in events:
        if isinstance(event, MessageSent) and event.message.channel_id == channel_id:
            msg = event.message
            sender_label = scenario.get_agent_display_name(agent_id=msg.sender_agent_id)
            lines.append(f"{sender_label}: {msg.text}")
    return "\n".join(lines)


def build_agent_transcript(
    events: list[SimulationEvent],
    agent_id: str,
    scenario: SimulationScenario,
) -> str:
    """Build a transcript of a single agent's messages and tool calls,
    labeled with channel/tool context from the agent's perspective.
    """
    lines: list[str] = []
    for event in events:
        if isinstance(event, MessageSent) and event.message.sender_agent_id == agent_id:
            msg = event.message
            label = scenario.get_channel_display_name(channel_id=msg.channel_id, agent_id=agent_id)
            lines.append(f"[{label}] {msg.text}")
        elif isinstance(event, LLMResponseReceived) and event.agent_id == agent_id:
            for tool_call in event.tool_calls:
                if tool_call.tool_name not in _MESSAGE_TOOLS:
                    formatted_args = _format_tool_args(arguments=tool_call.arguments)
                    lines.append(f"[{tool_call.tool_name}] {formatted_args}")
    return "\n".join(lines)
