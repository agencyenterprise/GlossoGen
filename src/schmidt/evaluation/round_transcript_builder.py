"""Builds per-round message transcripts from simulation events.

Extracts MessageSent events grouped by round number, with each message
labeled by the sender's display name. Used by generic evaluators that
analyze cross-round language evolution.
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

    Returns one RoundTranscript per round that had at least one message,
    sorted by round number.
    """
    messages_by_round: dict[int, list[str]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        rn = event.round_number
        sender = scenario.get_agent_display_name(
            agent_id=event.message.sender_agent_id,
        )
        line = f"{sender}: {event.message.text}"
        if rn not in messages_by_round:
            messages_by_round[rn] = []
        messages_by_round[rn].append(line)

    transcripts: list[RoundTranscript] = []
    for rn in sorted(messages_by_round.keys()):
        messages = messages_by_round[rn]
        transcripts.append(
            RoundTranscript(
                round_number=rn,
                transcript="\n".join(messages),
                message_count=len(messages),
            )
        )
    return transcripts
