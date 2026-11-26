"""Training sequences from the token ids that a run with ``record_token_ids=true`` logged.

``recorded_token_ids`` gives each of an agent's requests with its full prompt and the model's
answer, in the order in which the agent made them. ``player_sequences`` chains them. A sequence
starts with a request's prompt and answer. The next request extends it when its prompt starts
with the whole sequence so far, and a new sequence begins otherwise. A new sequence begins after
the runner restarts an agent's turn from an earlier point. The trainer therefore computes each
answer token's log-probability in the context in which vLLM sampled it.

Only the answer tokens are marked. Each marked token gets the advantage of its answer's round,
and the logprob that the policy server logged when it sampled the token. An answer's round is
the round of its first tool call. An answer without a tool call keeps the round of the agent's
previous call. A recorded answer without logged logprobs raises ``MissingSamplerLogprobs``.
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


class MissingSamplerLogprobs(ValueError):
    """A recorded answer holds token ids but no logprobs, which the loss needs."""


def sampler_logprobs(*, request: RecordedTokenIds) -> list[float]:
    """The logprob that the policy server logged for each token of the request's answer."""
    if request.token_logprobs is None:
        raise MissingSamplerLogprobs(
            f"an answer of round {request.round_number} holds token ids and no token_logprobs"
        )
    return request.token_logprobs


class SequenceInProgress:
    """The training sequence that ``player_sequences`` is chaining requests onto."""

    def __init__(self) -> None:
        self.input_ids: list[int] = []
        self.kl_mask: list[int] = []
        self.advantages: list[float] = []
        self.sampler_logprobs: list[float] = []

    def extended_by(self, *, request: RecordedTokenIds) -> bool:
        """Whether the request's prompt starts with the whole sequence so far."""
        return request.prompt_ids[: len(self.input_ids)] == self.input_ids

    def add(self, *, request: RecordedTokenIds, advantage: float) -> None:
        """Append the request's new prompt tokens, then its answer tokens, marked."""
        tail = request.prompt_ids[len(self.input_ids) :]
        answer = request.token_ids
        self.input_ids = self.input_ids + tail + answer
        self.kl_mask = self.kl_mask + [0] * len(tail) + [1] * len(answer)
        self.advantages = self.advantages + [0.0] * len(tail) + [advantage] * len(answer)
        self.sampler_logprobs = (
            self.sampler_logprobs + [0.0] * len(tail) + sampler_logprobs(request=request)
        )

    def sequence(self) -> TrainingSequence:
        """The sequence as the trainer takes it."""
        return TrainingSequence(
            input_ids=self.input_ids,
            kl_mask=self.kl_mask,
            advantages=self.advantages,
            sampler_logprobs=self.sampler_logprobs,
        )


def player_sequences(
    *, recorded: list[RecordedTokenIds], rounds: list[int], advantages: dict[int, float]
) -> PlayerSequences:
    """Chain one agent's recorded requests into training sequences, each answer marked."""
    if len(recorded) != len(rounds):
        raise ValueError(f"{len(recorded)} recorded requests, but {len(rounds)} answer rounds")
    sequences: list[TrainingSequence] = []
    current = SequenceInProgress()
    breaks = 0
    for request, round_number in zip(recorded, rounds, strict=True):
        if current.input_ids and not current.extended_by(request=request):
            sequences.append(current.sequence())
            breaks += 1
            current = SequenceInProgress()
        current.add(request=request, advantage=advantages.get(round_number, 0.0))
    if current.input_ids:
        sequences.append(current.sequence())
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
