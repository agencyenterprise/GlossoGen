"""The token ids and answer logprobs that a run with ``record_token_ids`` logged for one agent.

``recorded_token_ids`` rebuilds each recorded request's full prompt from the
``LLMResponseReceived`` events of one agent: the first ``prompt_prefix_tokens`` ids of
the agent's previous recorded prompt and answer, then ``prompt_tail_ids``. The events
are read in log order. ``token_ids_index`` starts at 0 when the agent's runner starts,
and at 0 the prefix is empty. Each recorded answer's ``token_logprobs`` hold one logprob
per answer token, or None when the event has no ``token_logprobs``.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import NamedTuple

from glossogen.models.event import LLMResponseReceived, SimulationEvent


class RecordedTokenIds(NamedTuple):
    """One recorded request: the ids of its prompt and of the model's answer, and the logprob of
    each answer token (None when the event has no ``token_logprobs``)."""

    round_number: int
    timestamp: datetime
    prompt_ids: list[int]
    token_ids: list[int]
    token_logprobs: list[float] | None


class TokenIdLogGap(ValueError):
    """An agent's recorded responses skip an index, so a prompt cannot be rebuilt."""


def recorded_token_ids(events: Sequence[SimulationEvent], agent_id: str) -> list[RecordedTokenIds]:
    """Return the agent's recorded requests in log order, with their full prompts."""
    recorded: list[RecordedTokenIds] = []
    previous: list[int] = []
    expected_index = 0
    for event in events:
        if not isinstance(event, LLMResponseReceived) or event.agent_id != agent_id:
            continue
        if (
            event.token_ids_index is None
            or event.prompt_prefix_tokens is None
            or event.prompt_tail_ids is None
            or event.token_ids is None
        ):
            continue
        if event.token_ids_index == 0:
            previous = []
        elif event.token_ids_index != expected_index:
            raise TokenIdLogGap(
                f"{agent_id}: recorded response {event.token_ids_index} follows "
                f"{expected_index - 1}"
            )
        prompt_ids = previous[: event.prompt_prefix_tokens] + event.prompt_tail_ids
        recorded.append(
            RecordedTokenIds(
                round_number=event.round_number,
                timestamp=event.timestamp,
                prompt_ids=prompt_ids,
                token_ids=event.token_ids,
                token_logprobs=event.token_logprobs,
            )
        )
        previous = prompt_ids + event.token_ids
        expected_index = event.token_ids_index + 1
    return recorded
