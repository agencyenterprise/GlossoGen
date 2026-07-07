"""Per-round collection of pristine primary-channel message texts.

Shared by surprisal-style metrics (``perplexity``, ``english_ngram_surprisal``)
that score the text agents composed on the scenario's primary channel. Each
``MessageSent`` is resolved to its pre-transform text via the pristine-text
index so the score reflects what the sender wrote, not what the channel
delivered (e.g. veyru's per-character channel noise).
"""

from typing import NamedTuple

from glossogen.evaluation.metric_core.pristine_text_index import pristine_text_for
from glossogen.models.event import MessageSent, SimulationEvent


class RoundMessages(NamedTuple):
    """All pristine primary-channel message texts for a single round."""

    round_number: int
    texts: list[str]


def collect_primary_messages_by_round(
    events: list[SimulationEvent],
    primary_channel_id: str,
    pristine_index: dict[str, str],
) -> list[RoundMessages]:
    """Extract pristine primary-channel message texts grouped by round.

    Each primary-channel ``MessageSent`` is resolved to its pre-transform text
    via ``pristine_index`` so the score reflects what the sender composed, not
    the channel-transformed delivery. Returns one ``RoundMessages`` per round
    that carried at least one non-empty message, sorted by round number.
    """
    by_round: dict[int, list[str]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id != primary_channel_id:
            continue
        text = pristine_text_for(index=pristine_index, message=event)
        if not text:
            continue
        if event.round_number not in by_round:
            by_round[event.round_number] = []
        by_round[event.round_number].append(text)
    return [RoundMessages(round_number=rn, texts=by_round[rn]) for rn in sorted(by_round.keys())]
