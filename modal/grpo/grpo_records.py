"""The records that the GRPO loop and the trainer exchange.

Both sides import this module: the loop on your machine, and the trainer in its Modal
container. It imports nothing outside the standard library, so the loop needs no torch.
"""

from typing import NamedTuple


class GrpoSettings(NamedTuple):
    """The trainer's settings, fixed for a whole training run."""

    lora_rank: int
    lora_alpha: int
    learning_rate: float
    kl_beta: float
    max_grad_norm: float
    logit_slice: int


class TrainingSequence(NamedTuple):
    """One stretch of a player's game as the model saw it, token by token.

    ``kl_mask`` marks the tokens that the policy sampled, the model's answers. ``advantages``
    gives each marked token the advantage of its round, and 0 to every other token.
    """

    input_ids: list[int]
    kl_mask: list[int]
    advantages: list[float]


class StepMetrics(NamedTuple):
    """What one training step measured.

    ``policy_loss`` and ``kl`` are means over the batch's marked tokens. The other fields are
    counts of tokens, the gradient norm, the step's duration and its peak GPU memory.
    """

    policy_loss: float
    kl: float
    marked_tokens: int
    advantaged_tokens: int
    tokens: int
    grad_norm: float
    clamped_tokens: int
    seconds: float
    peak_memory_gb: float
