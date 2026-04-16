"""Builds per-round message transcripts from simulation events.

Extracts MessageSent events grouped by round number, with each message
labeled by sender display name and channel. When a scenario declares a
primary channel, transcripts separate primary-channel messages from
secondary-channel context so evaluators can focus on the constrained
communication.
"""

import logging
from typing import NamedTuple

from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class RoundTranscript(NamedTuple):
    """All messages exchanged during a single round."""

    round_number: int
    transcript: str
    message_count: int


def build_round_transcripts(
    events: list[SimulationEvent],
    scenario: SimulationScenario,
) -> list[RoundTranscript]:
    """Group all MessageSent events by round and format as labeled transcripts.

    When the scenario declares a primary channel via ``get_primary_channel_id``,
    messages are split into a PRIMARY CHANNEL section and an OTHER CHANNELS
    section per round. Otherwise, all messages are listed together.

    Returns one RoundTranscript per round that had at least one message,
    sorted by round number.
    """
    primary_channel_id = scenario.get_primary_channel_id()

    primary_by_round: dict[int, list[str]] = {}
    other_by_round: dict[int, list[str]] = {}

    for event in events:
        if not isinstance(event, MessageSent):
            continue
        rn = event.round_number
        sender = scenario.get_agent_display_name(
            agent_id=event.message.sender_agent_id,
        )
        channel_name = scenario.get_channel_display_name(
            channel_id=event.message.channel_id,
            agent_id=event.message.sender_agent_id,
        )
        line = f"[{channel_name}] {sender}: {event.message.text}"

        if primary_channel_id is not None and event.message.channel_id == primary_channel_id:
            if rn not in primary_by_round:
                primary_by_round[rn] = []
            primary_by_round[rn].append(line)
        else:
            if rn not in other_by_round:
                other_by_round[rn] = []
            other_by_round[rn].append(line)

    all_rounds = sorted(set(primary_by_round.keys()) | set(other_by_round.keys()))

    transcripts: list[RoundTranscript] = []
    for rn in all_rounds:
        primary = primary_by_round.get(rn, [])
        other = other_by_round.get(rn, [])
        total_count = len(primary) + len(other)

        if primary_channel_id is not None:
            sections: list[str] = []
            if primary:
                sections.append("PRIMARY CHANNEL (budget-constrained):\n" + "\n".join(primary))
            if other:
                sections.append("OTHER CHANNELS:\n" + "\n".join(other))
            transcript_text = "\n\n".join(sections)
        else:
            transcript_text = "\n".join(primary + other)

        transcripts.append(
            RoundTranscript(
                round_number=rn,
                transcript=transcript_text,
                message_count=total_count,
            )
        )
    return transcripts
