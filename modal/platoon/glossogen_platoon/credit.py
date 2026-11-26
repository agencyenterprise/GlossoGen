"""``credit: glossogen-round-baseline``: per-round credit for signal_game, with a KL penalty to a
frozen policy.

Each seat's trajectory names one span per round (``glossogen_platoon.program``), in round order. A
call in a scored span trains on its span's reward minus the baseline of its seat in that round: the
mean span reward of the same role (seat) at the same place, over the group's agents that scored it.
The group is the games of one seed. Every other call trains on no round's score.

With ``kl_policy`` set, a frozen policy of ``policies:`` (the base model) scores every sampled
token, and each action token's advantage also gets ``-kl_coef * (sampled logprob - frozen
logprob)``. That difference estimates the KL divergence of the policy that sampled the token from
the frozen policy, so the penalty pulls the policy toward the frozen one. The group's mean of the k3
estimate, ``exp(r) - r - 1`` with ``r = frozen logprob - sampled logprob``, is logged as
``credit/glossogen/kl_k3``; with ``max_kl`` set, a group whose mean k3 is above it raises
``KlLimitExceeded``, which stops the run.

The options are all required: ``kl_policy`` (a frozen policy's id, or null), ``kl_coef`` (0 when
``kl_policy`` is null) and ``max_kl`` (null for no limit).
"""

from collections import defaultdict
from typing import Any, NamedTuple

import torch
from platoon.experimental import (
    CreditCheckContext,
    CreditEstimatorBase,
    CreditGroup,
    CreditSetup,
    TrainingSample,
    credit_estimator,
)
from pydantic import BaseModel, ConfigDict

ESTIMATOR_NAME = "glossogen-round-baseline"
KL_METRIC = "credit/glossogen/kl_k3"
PENALTY_METRIC = "credit/glossogen/kl_k1"


class KlLimitExceeded(RuntimeError):
    """A group's mean KL estimate to the frozen policy passed ``max_kl``."""


class RoundBaselineOptions(BaseModel):
    """``credit_options`` under ``credit: glossogen-round-baseline`` (the module's docstring)."""

    model_config = ConfigDict(extra="forbid")

    kl_policy: str | None
    kl_coef: float
    max_kl: float | None


class SpanKey(NamedTuple):
    """A round of one seat: the seat's role and the span's place among the seat's spans."""

    role: str
    index: int


class KlTotals(NamedTuple):
    """Sums over a group's action tokens: the k1 and k3 estimates, and the number of tokens."""

    k1: float
    k3: float
    tokens: int


def round_baselines(*, group: CreditGroup) -> dict[SpanKey, float]:
    """The mean span reward of each seat's round, over the group's agents that scored it."""
    rewards: dict[SpanKey, list[float]] = defaultdict(list)
    for agent in group.agents():
        for index, span in enumerate(agent.spans or ()):
            if span.reward is not None:
                rewards[SpanKey(role=agent.role, index=index)].append(span.reward)
    return {key: sum(values) / len(values) for key, values in rewards.items()}


def call_advantages(*, group: CreditGroup) -> dict[str, float]:
    """The advantage of each call in a scored span: its span's reward minus its seat's baseline in
    that round."""
    baselines = round_baselines(group=group)
    advantages: dict[str, float] = {}
    for agent in group.agents():
        for index, span in enumerate(agent.spans or ()):
            if span.reward is None:
                continue
            baseline = baselines[SpanKey(role=agent.role, index=index)]
            for call in span.calls:
                advantages[call] = span.reward - baseline
    return advantages


def sample_advantages(*, sample: TrainingSample, advantages: dict[str, float]) -> torch.Tensor:
    """One advantage per target token of a row: each call's tokens get its call's advantage, every
    other token 0."""
    values = torch.zeros_like(sample.advantages)
    for call, start, end in sample.calls:
        if call in advantages:
            values[start:end] = advantages[call]
    return values


def kl_totals(*, sampled: torch.Tensor, frozen: torch.Tensor, actions: torch.Tensor) -> KlTotals:
    """The sums of the k1 and k3 estimates over a row's action tokens."""
    log_ratio = frozen[actions] - sampled[actions]
    k3 = torch.exp(log_ratio) - log_ratio - 1.0
    return KlTotals(k1=float(-log_ratio.sum()), k3=float(k3.sum()), tokens=int(actions.sum()))


class RoundBaseline(CreditEstimatorBase):
    """Per-seat, per-round baselines over the group, with an optional KL penalty (the module's
    docstring)."""

    needs_agents = True
    reads_spans = True
    options_schema = RoundBaselineOptions
    options: RoundBaselineOptions

    def __init__(self, setup: CreditSetup, options: Any) -> None:
        """Lift the time limit of ``assign`` when it scores with a frozen policy, whose calls have
        their own."""
        super().__init__(setup=setup, options=options)
        if self.options.kl_policy is not None:
            self.assign_timeout_seconds = None

    @staticmethod
    def check(options: RoundBaselineOptions, ctx: CreditCheckContext) -> None:
        """Refuse a KL setting that names no frozen policy of the trained model, or a coefficient
        without one."""
        if options.kl_policy is None:
            if options.kl_coef != 0.0 or options.max_kl is not None:
                raise ValueError("kl_coef must be 0 and max_kl null when kl_policy is null")
            return
        declared = ctx.config.policies
        if options.kl_policy not in declared:
            raise ValueError(f"kl_policy: {options.kl_policy!r} is not a policy of policies:")
        frozen = declared[options.kl_policy]
        if frozen.trainable:
            raise ValueError(f"kl_policy: policies.{options.kl_policy} trains; it must be frozen")
        trained = [ctx.config.train.model_name] + [
            policy.model_name for policy in declared.values() if policy.trainable
        ]
        if any(model != frozen.model_name for model in trained):
            raise ValueError(
                f"kl_policy: policies.{options.kl_policy} is another model than a trained policy"
            )

    async def assign(self, group: CreditGroup) -> None:
        """Set each row's round advantages, then subtract the KL penalty when a frozen policy is
        named."""
        samples = group.samples()
        advantages = call_advantages(group=group)
        values = [sample_advantages(sample=sample, advantages=advantages) for sample in samples]
        if self.options.kl_policy is not None and samples:
            values = await self.penalized(group=group, samples=samples, values=values)
        for sample, sample_values in zip(samples, values, strict=True):
            sample.set_advantages(sample_values)

    async def penalized(
        self, *, group: CreditGroup, samples: list[TrainingSample], values: list[torch.Tensor]
    ) -> list[torch.Tensor]:
        """``values`` with the KL penalty on every action token, after checking the group's mean
        KL."""
        frozen_policy = group.policies[str(self.options.kl_policy)]
        scores = await frozen_policy.score(datums=[sample.datum for sample in samples])
        penalized: list[torch.Tensor] = []
        totals = KlTotals(k1=0.0, k3=0.0, tokens=0)
        for sample, sample_values, frozen in zip(samples, values, scores, strict=True):
            sampled = sample.datum.loss_fn_inputs["logprobs"].to_torch()
            actions = sample.mask > 0
            row = kl_totals(sampled=sampled, frozen=frozen, actions=actions)
            totals = KlTotals(
                k1=totals.k1 + row.k1, k3=totals.k3 + row.k3, tokens=totals.tokens + row.tokens
            )
            penalty = torch.where(actions, sampled - frozen, torch.zeros_like(sampled))
            penalized.append(sample_values - self.options.kl_coef * penalty)
        self.record_kl(group=group, totals=totals)
        return penalized

    def record_kl(self, *, group: CreditGroup, totals: KlTotals) -> None:
        """Log the group's mean KL estimates, and stop the run when the mean k3 passes
        ``max_kl``."""
        if totals.tokens == 0:
            return
        mean_k3 = totals.k3 / totals.tokens
        group.stats.scalar(**{KL_METRIC: mean_k3, PENALTY_METRIC: totals.k1 / totals.tokens})
        if self.options.max_kl is not None and mean_k3 > self.options.max_kl:
            raise KlLimitExceeded(
                f"group {group.task_id}: mean KL estimate {mean_k3:.4f} "
                f"is above max_kl {self.options.max_kl}"
            )


credit_estimator(ESTIMATOR_NAME)(RoundBaseline)
