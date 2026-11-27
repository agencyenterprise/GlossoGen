"""The run as the protocol-agreement judge reads it: every message and tool call, with references.

Each entry carries a short reference such as ``R3.12`` for the judge to cite, and the id
the run page uses for the same entry, so a citation can be turned into a link. Tool
calls keep their arguments, where scenarios record what an action was meant to signal.
Tool results are left out: they repeat what the scenario showed the agent, and in
some scenarios they are long enough to crowd out the agents' own words.
"""

import json
from typing import NamedTuple

from glossogen.models.communication_tool_names import (
    GET_CHANNEL_MEMBERS_TOOL_NAME,
    LIST_CHANNELS_TOOL_NAME,
    READ_CHANNEL_TOOL_NAME,
    SEND_MESSAGE_TOOL_NAME,
)
from glossogen.models.event import MessageSent, SimulationEvent, ToolCallInvoked
from glossogen.models.read_notifications_schema import READ_NOTIFICATIONS_TOOL_NAME

# Calls that carry no signal of their own. A sent message is listed from its
# ``message_sent`` event instead, under the id the run page gives it.
_PLATFORM_TOOL_NAMES = frozenset(
    {
        GET_CHANNEL_MEMBERS_TOOL_NAME,
        LIST_CHANNELS_TOOL_NAME,
        READ_CHANNEL_TOOL_NAME,
        READ_NOTIFICATIONS_TOOL_NAME,
        SEND_MESSAGE_TOOL_NAME,
    }
)


class CitedEntry(NamedTuple):
    """One message or tool call, with the reference the judge cites and the run page's id."""

    reference: str
    message_id: str
    round_number: int
    agent_id: str
    text: str


class CitedRound(NamedTuple):
    """The entries of one round, rendered one per line for the judge."""

    round_number: int
    entry_count: int
    transcript: str


def build_cited_entries(events: list[SimulationEvent]) -> list[CitedEntry]:
    """List the run's channel messages and scenario tool calls in log order, with references."""
    entries: list[CitedEntry] = []
    count_by_round: dict[int, int] = {}
    for event in events:
        if isinstance(event, MessageSent):
            message = event.message
            message_id = message.message_id
            agent_id = message.sender_agent_id
            text = f"#{message.channel_id}: {message.text}"
        elif isinstance(event, ToolCallInvoked) and event.tool_name not in _PLATFORM_TOOL_NAMES:
            message_id = f"{event.event_id}-{event.call_id}"
            agent_id = event.agent_id
            text = f"{event.tool_name} {json.dumps(event.arguments, ensure_ascii=False)}"
        else:
            continue
        position = count_by_round.get(event.round_number, 0) + 1
        count_by_round[event.round_number] = position
        entries.append(
            CitedEntry(
                reference=f"R{event.round_number}.{position}",
                message_id=message_id,
                round_number=event.round_number,
                agent_id=agent_id,
                text=text,
            )
        )
    return entries


def render_cited_rounds(entries: list[CitedEntry]) -> list[CitedRound]:
    """Group ``entries`` by round, one line per entry: reference, agent, then the entry."""
    lines_by_round: dict[int, list[str]] = {}
    for entry in entries:
        line = f"[{entry.reference}] {entry.agent_id}: {entry.text}"
        lines_by_round.setdefault(entry.round_number, []).append(line)
    return [
        CitedRound(round_number=round_number, entry_count=len(lines), transcript="\n".join(lines))
        for round_number, lines in sorted(lines_by_round.items())
    ]
