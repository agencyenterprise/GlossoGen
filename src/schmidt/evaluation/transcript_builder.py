"""Builds formatted transcripts from simulation events for use by evaluators.

Extracts messages and tool calls from the event log and formats them into
human-readable transcripts. Tool calls are formatted generically using their
argument names and values.
"""

import logging
from typing import Any

from schmidt.models.event import MessageSent, SimulationEvent, ToolCalled
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


def _format_tool_args(arguments: dict[str, Any]) -> str:
    """Format tool call arguments as a comma-separated key=value string."""
    return ", ".join(f"{k}={v}" for k, v in arguments.items())


def build_full_transcript(
    events: list[SimulationEvent],
    scenario: SimulationScenario,
) -> str:
    """Build a chronological transcript of all messages and tool calls,
    labeled with sender and channel/tool context.
    """
    lines: list[str] = []
    for event in events:
        if isinstance(event, MessageSent):
            msg = event.message
            sender_label = scenario.get_agent_display_name(agent_id=msg.sender_agent_id)
            lines.append(f"[{msg.channel_id}] {sender_label}: {msg.text}")
        elif isinstance(event, ToolCalled):
            sender_label = scenario.get_agent_display_name(agent_id=event.agent_id)
            formatted_args = _format_tool_args(arguments=event.request.arguments)
            lines.append(f"[{event.request.tool_name}] {sender_label}: {formatted_args}")
    return "\n".join(lines)


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
        elif isinstance(event, ToolCalled) and event.agent_id == agent_id:
            formatted_args = _format_tool_args(arguments=event.request.arguments)
            lines.append(f"[{event.request.tool_name}] {formatted_args}")
    return "\n".join(lines)
