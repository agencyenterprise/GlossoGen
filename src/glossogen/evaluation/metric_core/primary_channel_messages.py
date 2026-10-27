"""Per-round collection of primary-channel message texts.

The caller picks which text of a ``MessageSent`` counts: the text the channel
delivered (``transmitted_text``), or the text the sender composed before a
channel transform rewrote it (``pristine_text_for``).
"""

from typing import NamedTuple, Protocol

from glossogen.models.event import MessageSent, SimulationEvent


class MessageText(Protocol):
    """Picks the text of a ``MessageSent`` that a metric scores."""

    def __call__(self, message: MessageSent) -> str:
        """Return the text of ``message`` to score."""
        ...


class RoundMessages(NamedTuple):
    """All primary-channel message texts for a single round."""

    round_number: int
    texts: list[str]


def transmitted_text(message: MessageSent) -> str:
    """Return the text the channel delivered for ``message``."""
    return message.message.text


def collect_primary_messages_by_round(
    events: list[SimulationEvent],
    channel_ids: frozenset[str],
    text_of: MessageText,
) -> list[RoundMessages]:
    """Extract the text ``text_of`` picks from each message on ``channel_ids``, by round.

    Returns one ``RoundMessages`` per round that carried at least one non-empty
    message, sorted by round number.
    """
    by_round: dict[int, list[str]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id not in channel_ids:
            continue
        text = text_of(message=event)
        if not text:
            continue
        if event.round_number not in by_round:
            by_round[event.round_number] = []
        by_round[event.round_number].append(text)
    return [RoundMessages(round_number=rn, texts=by_round[rn]) for rn in sorted(by_round.keys())]
