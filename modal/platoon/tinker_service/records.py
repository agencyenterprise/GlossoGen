"""The records that the service and its backends exchange, decoded from the Tinker API's wire
types."""

from typing import NamedTuple


class TrainingRow(NamedTuple):
    """One datum of a ``forward_backward`` request.

    ``input_tokens`` is the datum's model input, and ``target_tokens`` the token each position
    predicts: the input shifted by one, followed by one more token. ``sampling_logprobs``,
    ``advantages`` and ``weights`` hold one value per target token, or None when the request did not
    send them.
    """

    input_tokens: list[int]
    target_tokens: list[int]
    sampling_logprobs: list[float] | None
    advantages: list[float] | None
    weights: list[float] | None


class RowOutput(NamedTuple):
    """What ``forward_backward`` computed for one row: one logprob per target token, and the row's
    loss."""

    logprobs: list[float]
    loss: float


class AdamSettings(NamedTuple):
    """The optimizer settings of one ``optim_step`` request."""

    learning_rate: float
    beta1: float
    beta2: float
    eps: float
    weight_decay: float
    grad_clip_norm: float


class SamplingRequest(NamedTuple):
    """One ``asample`` request: the prompt's tokens and how to sample after them.

    A ``stop`` of the Tinker API is either strings or token ids, so one of ``stop_strings`` and
    ``stop_tokens`` is empty. With ``prompt_logprobs``, the response also gives the logprob of each
    prompt token.
    """

    prompt: list[int]
    max_tokens: int | None
    temperature: float
    top_k: int
    top_p: float
    seed: int | None
    stop_strings: list[str]
    stop_tokens: list[int]
    num_samples: int
    prompt_logprobs: bool


class SampledSequence(NamedTuple):
    """One sampled sequence: its tokens, the logprob of each, and ``stop`` or ``length``."""

    tokens: list[int]
    logprobs: list[float]
    stop_reason: str


class SampleResult(NamedTuple):
    """What a sampling backend returns: the sequences, and each prompt token's logprob when asked
    for.

    The first prompt token has no logprob, so ``prompt_logprobs`` starts with None.
    """

    sequences: list[SampledSequence]
    prompt_logprobs: list[float | None] | None


class AdapterInfo(NamedTuple):
    """What a checkpoint folder records about its adapter: the base model and the LoRA rank."""

    base_model: str
    rank: int
