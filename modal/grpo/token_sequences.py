"""Training sequences from the token ids that a run with ``record_token_ids=true`` logged.

``recorded_token_ids`` gives each of an agent's requests with its full prompt and the model's
answer, in the order in which the agent made them. ``player_sequences`` chains them. A sequence
starts with a request's prompt and answer. The next request extends it when its prompt starts
with the whole sequence so far, and starts a new sequence otherwise. A new sequence starts after
the runner restarts an agent's turn from an earlier point.

Only the answer tokens are marked. Each marked token gets the advantage of its answer's round.
An answer's round is the round of its first tool call. An answer without a tool call keeps the
round of the agent's previous call. The trainer therefore computes each answer token's
log-probability in the context in which vLLM sampled it.
"""

from typing import NamedTuple

from grpo_records import TrainingSequence

from glossogen.models.event import LLMResponseReceived, SimulationEvent, ToolCallInvoked
from glossogen.run_storage.recorded_token_ids import RecordedTokenIds, recorded_token_ids


class PlayerSequences(NamedTuple):
    """One agent's training sequences from one game, and counts that describe them."""

    sequences: list[TrainingSequence]
    answers: int
    answer_tokens: int
    sequence_tokens: int
    chain_breaks: int


def recorded_responses(
    *, events: list[SimulationEvent], agent_id: str
) -> list[LLMResponseReceived]:
    """The agent's responses that hold token ids.

    They are the responses that ``recorded_token_ids`` reads, in the same order.
    """
    return [
        event
        for event in events
        if isinstance(event, LLMResponseReceived)
        and event.agent_id == agent_id
        and event.token_ids_index is not None
        and event.prompt_prefix_tokens is not None
        and event.prompt_tail_ids is not None
        and event.token_ids is not None
    ]


def answer_rounds(*, events: list[SimulationEvent], agent_id: str) -> list[int]:
    """The round of each recorded answer of the agent, in order."""
    call_round = {
        event.call_id: event.round_number for event in events if isinstance(event, ToolCallInvoked)
    }
    rounds: list[int] = []
    current = 0
    for response in recorded_responses(events=events, agent_id=agent_id):
        if response.tool_calls:
            current = call_round[response.tool_calls[0].call_id]
        rounds.append(current)
    return rounds


def player_sequences(
    *, recorded: list[RecordedTokenIds], rounds: list[int], advantages: dict[int, float]
) -> PlayerSequences:
    """Chain one agent's recorded requests into training sequences, each answer marked."""
    if len(recorded) != len(rounds):
        raise ValueError(f"{len(recorded)} recorded requests, but {len(rounds)} answer rounds")
    sequences: list[TrainingSequence] = []
    input_ids: list[int] = []
    kl_mask: list[int] = []
    marked_advantages: list[float] = []
    breaks = 0
    for request, round_number in zip(recorded, rounds, strict=True):
        extends = request.prompt_ids[: len(input_ids)] == input_ids
        if input_ids and not extends:
            sequences.append(
                TrainingSequence(input_ids=input_ids, kl_mask=kl_mask, advantages=marked_advantages)
            )
            breaks += 1
            input_ids, kl_mask, marked_advantages = [], [], []
        tail = request.prompt_ids[len(input_ids) :]
        advantage = advantages.get(round_number, 0.0)
        input_ids = input_ids + tail + request.token_ids
        kl_mask = kl_mask + [0] * len(tail) + [1] * len(request.token_ids)
        marked_advantages = (
            marked_advantages + [0.0] * len(tail) + [advantage] * len(request.token_ids)
        )
    if input_ids:
        sequences.append(
            TrainingSequence(input_ids=input_ids, kl_mask=kl_mask, advantages=marked_advantages)
        )
    return PlayerSequences(
        sequences=sequences,
        answers=len(recorded),
        answer_tokens=sum(len(request.token_ids) for request in recorded),
        sequence_tokens=sum(len(sequence.input_ids) for sequence in sequences),
        chain_breaks=breaks,
    )


def game_sequences(
    *, events: list[SimulationEvent], agent_id: str, advantages: dict[int, float]
) -> PlayerSequences:
    """One agent's training sequences from one game's event log."""
    return player_sequences(
        recorded=recorded_token_ids(events=events, agent_id=agent_id),
        rounds=answer_rounds(events=events, agent_id=agent_id),
        advantages=advantages,
    )
