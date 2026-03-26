"""Reconstructs a per-agent conversation transcript from JSONL events.

Extracts structured conversation entries from the event log and renders them
via a Jinja2 template. Used by the fork system to give agents full context
of the prior conversation when resuming.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from schmidt.models.event import (
    AgentRegistered,
    InjectionDelivered,
    MessageSent,
    RoundAdvanced,
    SimulationEvent,
)
from schmidt.template_renderer import TemplateRenderer

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "runners" / "prompts"


def build_agent_context(
    events: list[SimulationEvent],
    agent_id: str,
    target_message_id: str,
    message_edits: dict[str, str],
) -> str:
    """Build a conversation transcript for an agent up to a target message.

    Extracts structured entries (round transitions, injections, messages)
    and renders them via the ``fork_context.jinja`` template. Does not
    include the agent's prior reasoning — only externally visible state.
    """
    display_names = _build_display_name_map(events=events)
    agent_display_name = display_names.get(agent_id, agent_id)
    entries = _extract_entries(
        events=events,
        agent_id=agent_id,
        target_message_id=target_message_id,
        message_edits=message_edits,
    )
    renderer = TemplateRenderer(prompts_dir=PROMPTS_DIR)
    return renderer.render(
        template_name="fork_context.jinja",
        template_variables={
            "entries": entries,
            "agent_display_name": agent_display_name,
        },
    )


def _extract_entries(
    events: list[SimulationEvent],
    agent_id: str,
    target_message_id: str,
    message_edits: dict[str, str],
) -> list[dict[str, Any]]:
    """Walk events up to the target message and collect structured entries."""
    target_ts = _find_target_timestamp(
        events=events,
        target_message_id=target_message_id,
    )

    agent_channels = _get_agent_channels(events=events, agent_id=agent_id)
    display_names = _build_display_name_map(events=events)

    entries: list[dict[str, Any]] = []

    for event in events:
        if event.timestamp > target_ts:
            break

        if isinstance(event, RoundAdvanced):
            entries.append(
                {
                    "type": "round",
                    "round_number": event.new_round_number,
                }
            )

        elif isinstance(event, InjectionDelivered) and event.agent_id == agent_id:
            entries.append(
                {
                    "type": "injection",
                    "text": event.text,
                }
            )

        elif isinstance(event, MessageSent):
            msg = event.message
            if msg.channel_id not in agent_channels:
                continue

            text = msg.text
            if msg.message_id in message_edits:
                text = message_edits[msg.message_id]

            sender_label = display_names.get(msg.sender_agent_id, msg.sender_agent_id)

            entries.append(
                {
                    "type": "message",
                    "channel_id": msg.channel_id,
                    "sender": sender_label,
                    "text": text,
                }
            )

    return entries


def _find_target_timestamp(
    events: list[SimulationEvent],
    target_message_id: str,
) -> datetime:
    """Find the timestamp of the target MessageSent event."""
    for event in events:
        if isinstance(event, MessageSent) and event.message.message_id == target_message_id:
            return event.timestamp
    raise ValueError(f"No MessageSent with message_id={target_message_id!r}")


def _get_agent_channels(
    events: list[SimulationEvent],
    agent_id: str,
) -> set[str]:
    """Extract the channel IDs visible to an agent from AgentRegistered events."""
    for event in events:
        if isinstance(event, AgentRegistered) and event.agent_id == agent_id:
            return set(event.channel_ids)
    return set()


def _build_display_name_map(events: list[SimulationEvent]) -> dict[str, str]:
    """Build an agent_id → role_name mapping from AgentRegistered events."""
    names: dict[str, str] = {}
    for event in events:
        if isinstance(event, AgentRegistered):
            names[event.agent_id] = event.role_name
    return names
