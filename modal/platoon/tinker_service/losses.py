"""The Tinker API's loss functions, as one row's loss from the trained policy's logprobs of its
target tokens.

Each loss is a sum over the row's target tokens, with no normalization: the client scales advantages
and weights, as the Tinker API specifies. With ``ratio = exp(logprob - sampling logprob)``:

- ``cross_entropy``: ``-weights * logprob``;
- ``importance_sampling``: ``-ratio * advantage``;
- ``ppo``: ``-min(ratio * advantage, clamp(ratio, low, high) * advantage)``, with low and high 0.8
  and 1.2 unless ``loss_fn_config`` gives ``clip_low_threshold`` and ``clip_high_threshold``;
- ``cispo``: ``-stopgrad(clamp(ratio, low, high)) * logprob * advantage``, with low and high 0 and 4
  unless the config gives them.

Only the positions that a loss reads need a logprob (``active_positions``): those with a nonzero
weight, advantage or sampling logprob. The others get 0 in the response.
"""

from collections.abc import Callable
from typing import NamedTuple

import torch
from tinker_service.records import TrainingRow


class ClipRange(NamedTuple):
    """The lowest and the highest importance ratio a clipped loss keeps."""

    low: float
    high: float


class RatioTerms(NamedTuple):
    """Each token's importance ratio and its advantage."""

    ratio: torch.Tensor
    advantages: torch.Tensor


PPO_CLIP = ClipRange(low=0.8, high=1.2)
CISPO_CLIP = ClipRange(low=0.0, high=4.0)


def as_tensor(*, values: list[float] | None, like: torch.Tensor, name: str) -> torch.Tensor:
    """``values`` as a tensor of ``like``'s dtype and device; refuse a row without them."""
    if values is None:
        raise ValueError(f"the loss needs {name}, and the datum has none")
    return torch.tensor(values, dtype=like.dtype, device=like.device)


def clip_range(*, config: dict[str, float], defaults: ClipRange) -> ClipRange:
    """The clip thresholds of ``config``, each one it leaves out at its default."""
    return ClipRange(
        low=config.get("clip_low_threshold", defaults.low),
        high=config.get("clip_high_threshold", defaults.high),
    )


def cross_entropy(
    *, logprobs: torch.Tensor, row: TrainingRow, config: dict[str, float]
) -> torch.Tensor:
    """``-sum(weights * logprob)``."""
    del config
    weights = as_tensor(values=row.weights, like=logprobs, name="weights")
    return -(weights * logprobs).sum()


def ratio_terms(*, logprobs: torch.Tensor, row: TrainingRow) -> RatioTerms:
    """The importance ratio of each token, and its advantage."""
    sampling = as_tensor(values=row.sampling_logprobs, like=logprobs, name="logprobs")
    advantages = as_tensor(values=row.advantages, like=logprobs, name="advantages")
    return RatioTerms(ratio=torch.exp(logprobs - sampling), advantages=advantages)


def importance_sampling(
    *, logprobs: torch.Tensor, row: TrainingRow, config: dict[str, float]
) -> torch.Tensor:
    """``-sum(ratio * advantage)``."""
    del config
    terms = ratio_terms(logprobs=logprobs, row=row)
    return -(terms.ratio * terms.advantages).sum()


def ppo(*, logprobs: torch.Tensor, row: TrainingRow, config: dict[str, float]) -> torch.Tensor:
    """The clipped surrogate objective, negated."""
    clip = clip_range(config=config, defaults=PPO_CLIP)
    terms = ratio_terms(logprobs=logprobs, row=row)
    clipped = torch.clamp(terms.ratio, clip.low, clip.high) * terms.advantages
    return -torch.minimum(terms.ratio * terms.advantages, clipped).sum()


def cispo(*, logprobs: torch.Tensor, row: TrainingRow, config: dict[str, float]) -> torch.Tensor:
    """``-sum(stopgrad(clamp(ratio)) * logprob * advantage)``."""
    clip = clip_range(config=config, defaults=CISPO_CLIP)
    terms = ratio_terms(logprobs=logprobs, row=row)
    coefficient = torch.clamp(terms.ratio, clip.low, clip.high).detach()
    return -(coefficient * logprobs * terms.advantages).sum()


LossFunction = Callable[..., torch.Tensor]
LOSS_FUNCTIONS: dict[str, LossFunction] = {
    "cross_entropy": cross_entropy,
    "importance_sampling": importance_sampling,
    "ppo": ppo,
    "cispo": cispo,
}


def loss_function(*, name: str) -> LossFunction:
    """The loss function named ``name``; refuse one the service does not implement."""
    if name not in LOSS_FUNCTIONS:
        raise ValueError(f"loss_fn {name!r} is not one of {sorted(LOSS_FUNCTIONS)}")
    return LOSS_FUNCTIONS[name]


def active_positions(*, row: TrainingRow) -> torch.Tensor:
    """Which target tokens a loss reads: those with a nonzero weight, advantage or sampling
    logprob."""
    active = torch.zeros(len(row.target_tokens), dtype=torch.bool)
    for values in (row.weights, row.advantages, row.sampling_logprobs):
        if values is not None:
            active |= torch.tensor(values) != 0
    return active


def row_loss(
    *, loss_fn: str, config: dict[str, float], logprobs: torch.Tensor, row: TrainingRow
) -> torch.Tensor:
    """The loss of ``row``, from the logprobs of its target tokens at its active positions."""
    active = active_positions(row=row).to(logprobs.device)
    selected = row._replace(
        target_tokens=[token for token, keep in zip(row.target_tokens, active.tolist()) if keep],
        sampling_logprobs=selected_values(values=row.sampling_logprobs, active=active),
        advantages=selected_values(values=row.advantages, active=active),
        weights=selected_values(values=row.weights, active=active),
    )
    return loss_function(name=loss_fn)(logprobs=logprobs, row=selected, config=config)


def selected_values(*, values: list[float] | None, active: torch.Tensor) -> list[float] | None:
    """The values at the active positions, or None when there are none."""
    if values is None:
        return None
    return [value for value, keep in zip(values, active.tolist()) if keep]
