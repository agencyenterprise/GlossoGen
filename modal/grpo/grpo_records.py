"""The records that the GRPO loop and the trainer exchange.

Both sides import this module: the loop on your machine, and the trainer in its Modal
container. It imports nothing outside the standard library, so the loop needs no torch.
"""

from typing import NamedTuple

BASE_MODEL = "Qwen/Qwen3.8-27B"
"""The model that the trainer adapts. The policy server also serves it, unadapted, under this
name."""


class GrpoSettings(NamedTuple):
    """The trainer's settings, fixed for a whole training run.

    ``ratio_cap`` is the largest importance weight that the loss gives an answer token.
    """

    lora_rank: int
    lora_alpha: int
    learning_rate: float
    kl_beta: float
    max_grad_norm: float
    logit_slice: int
    ratio_cap: float


class TrainingSequence(NamedTuple):
    """One stretch of a player's game as the model saw it, token by token.

    ``kl_mask`` marks the tokens that the policy sampled, the model's answers. ``advantages``
    gives each marked token the advantage of its round, and 0 to every other token.
    ``sampler_logprobs`` gives each marked token the logprob that the policy server logged when
    it sampled the token, and 0 to every other token.
    """

    input_ids: list[int]
    kl_mask: list[int]
    advantages: list[float]
    sampler_logprobs: list[float]


class StepMetrics(NamedTuple):
    """What one training step measured.

    ``policy_loss`` and ``kl`` are means over the batch's marked tokens. ``ratio_mean`` and
    ``ratio_max`` describe the importance ratio of the marked tokens before the cap, and
    ``ratio_capped_share`` is the share of them whose ratio was above the cap. The other fields
    are counts of tokens, the gradient norm, the step's duration and its peak GPU memory.
    ``clamped_tokens`` counts the tokens whose k3 was clamped.
    """

    policy_loss: float
    kl: float
    marked_tokens: int
    advantaged_tokens: int
    tokens: int
    grad_norm: float
    clamped_tokens: int
    ratio_mean: float
    ratio_max: float
    ratio_capped_share: float
    seconds: float
    peak_memory_gb: float
