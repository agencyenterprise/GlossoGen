"""Builds per-round message transcripts from simulation events.

Extracts MessageSent events grouped by round number, with each message
labeled by sender display name and channel. When a scenario declares a
primary channel, transcripts separate primary-channel messages from
secondary-channel context so evaluators can focus on the constrained
communication.
"""

import logging
from typing import NamedTuple

from schmidt.evaluation.metric_core.pristine_text_index import pristine_text_for
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
    pristine_index: dict[str, str],
) -> list[RoundTranscript]:
    """Group all MessageSent events by round and format as labeled transcripts.

    When the scenario declares primary channels via ``get_primary_channels``,
    messages are split into a PRIMARY CHANNEL section and an OTHER CHANNELS
    section per round. Otherwise, all messages are listed together.

    Each message line uses ``pristine_text_for(index=pristine_index, ...)`` to
    resolve its text: callers that pass a populated ``pristine_index`` (from
    ``build_pristine_text_index``) render the text the sender composed before any
    ``transform_outgoing_message`` rewrite (e.g. veyru's channel noise); callers
    that pass an empty dict render the transmitted text as persisted.

    Returns one RoundTranscript per round that had at least one message,
    sorted by round number.
    """
    primary_channel_ids = {channel.channel_id for channel in scenario.get_primary_channels()}

    primary_by_round: dict[int, list[str]] = {}
    other_by_round: dict[int, list[str]] = {}

    for event in events:
        if not isinstance(event, MessageSent):
            continue
        rn = event.round_number
        sender = scenario.get_agent_display_name_at_round(
            agent_id=event.message.sender_agent_id,
            round_number=rn,
        )
        channel_name = scenario.get_channel_display_name(
            channel_id=event.message.channel_id,
            agent_id=event.message.sender_agent_id,
        )
        text = pristine_text_for(index=pristine_index, message=event)
        line = f"[{channel_name}] {sender}: {text}"

        if event.message.channel_id in primary_channel_ids:
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

        if primary_channel_ids:
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
