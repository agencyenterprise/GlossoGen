"""Per-round grouping of the messages sent on a set of channels.

``group_messages_by_round`` groups the ``MessageSent`` events themselves.
``collect_primary_messages_by_round`` reduces them to the texts a metric scores;
the caller picks which text of a ``MessageSent`` counts: the text the channel
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


class RoundMessageEvents(NamedTuple):
    """The ``MessageSent`` events on a set of channels in one round, in log order."""

    round_number: int
    messages: list[MessageSent]


class RoundMessages(NamedTuple):
    """All primary-channel message texts for a single round."""

    round_number: int
    texts: list[str]


def transmitted_text(message: MessageSent) -> str:
    """Return the text the channel delivered for ``message``."""
    return message.message.text


def group_messages_by_round(
    events: list[SimulationEvent],
    channel_ids: frozenset[str],
) -> list[RoundMessageEvents]:
    """Group the ``MessageSent`` events on ``channel_ids`` by round, in log order.

    Returns one ``RoundMessageEvents`` per round that carried at least one such
    message, sorted by round number.
    """
    by_round: dict[int, list[MessageSent]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id not in channel_ids:
            continue
        by_round.setdefault(event.round_number, []).append(event)
    return [
        RoundMessageEvents(round_number=rn, messages=by_round[rn]) for rn in sorted(by_round.keys())
    ]


def collect_primary_messages_by_round(
    events: list[SimulationEvent],
    channel_ids: frozenset[str],
    text_of: MessageText,
) -> list[RoundMessages]:
    """Extract the text ``text_of`` picks from each message on ``channel_ids``, by round.

    Returns one ``RoundMessages`` per round that carried at least one non-empty
    message, sorted by round number.
    """
    rounds: list[RoundMessages] = []
    for round_messages in group_messages_by_round(events=events, channel_ids=channel_ids):
        texts = [text_of(message=message) for message in round_messages.messages]
        non_empty = [text for text in texts if text]
        if non_empty:
            rounds.append(RoundMessages(round_number=round_messages.round_number, texts=non_empty))
    return rounds
