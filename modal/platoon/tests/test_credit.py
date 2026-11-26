"""The per-round credit estimator: each round's calls train on the round's score minus the seat's
mean in that round over the seed's games, and a frozen policy's scores add a KL penalty and a KL
limit."""

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
import torch
from episodes import credit_group, seat_trajectories
from glossogen_platoon.credit import (
    ESTIMATOR_NAME,
    KlLimitExceeded,
    RoundBaseline,
    RoundBaselineOptions,
)
from platoon.experimental import CreditCheckContext, CreditSetup, PolicyView
from platoon.testing import EpisodeRun, check_credit_estimator
from platoon.testing.policy import DEFAULT_LOGPROB
from platoon.train.config_defs import WorkflowConfig
from platoon.train.policy.spec import MAIN

TASK_ID = "seed-1000"
FROZEN_LOGPROB = -1.0
KL_COEF = 0.5
NO_KL = {"kl_policy": None, "kl_coef": 0.0, "max_kl": None}


def estimator(*, options: dict[str, Any]) -> RoundBaseline:
    """The estimator, built as a run builds it."""
    setup = CreditSetup(
        name=ESTIMATOR_NAME, entry="signal-game", settings=WorkflowConfig(), policies=(MAIN, "base")
    )
    return RoundBaseline(setup=setup, options=RoundBaselineOptions.model_validate(options))


async def frozen_scores(datums: Sequence[Any]) -> list[torch.Tensor]:
    """A frozen policy that gives every target token the same logprob."""
    return [
        torch.full_like(datum.loss_fn_inputs["logprobs"].to_torch(), FROZEN_LOGPROB)
        for datum in datums
    ]


def expected_call_advantages(*, runs: list[EpisodeRun]) -> dict[str, float]:
    """Each call's round score minus its seat's mean in that round, by the tutorial loop's rule."""
    expected: dict[str, float] = {}
    for seat in ("player_a", "player_b"):
        spans = [seat_trajectories(run=run)[seat].misc["spans"] for run in runs]
        for index in range(len(spans[0])):
            mean = sum(game[index]["reward"] for game in spans) / len(spans)
            for game in spans:
                for call in game[index]["calls"]:
                    expected[call] = game[index]["reward"] - mean
    return expected


def action_advantages(*, group: Any) -> dict[str, set[float]]:
    """The advantages the group's rows give each call's tokens, rounded."""
    found: dict[str, set[float]] = {}
    for sample in group.samples():
        for call, start, end in sample.calls:
            values = {round(value, 4) for value in sample.advantages[start:end].tolist()}
            found.setdefault(call, set()).update(values)
    return found


def test_the_estimator_passes_platoon_s_conformance_check() -> None:
    check_credit_estimator(RoundBaseline, options=NO_KL)


async def test_each_round_trains_on_its_score_minus_the_seat_mean(
    first_item_group: list[EpisodeRun],
) -> None:
    group = credit_group(runs=first_item_group, task_id=TASK_ID, policies={})
    await estimator(options=NO_KL).assign(group)
    expected = expected_call_advantages(runs=first_item_group)
    found = action_advantages(group=group)
    assert found
    for call, values in found.items():
        assert values == {round(expected.get(call, 0.0), 4)}


async def test_the_kl_penalty_is_the_sampled_minus_the_frozen_logprob(
    first_item_group: list[EpisodeRun],
) -> None:
    base = PolicyView(id="base", scorer=frozen_scores)
    group = credit_group(runs=first_item_group, task_id=TASK_ID, policies={"base": base})
    options = {"kl_policy": "base", "kl_coef": KL_COEF, "max_kl": None}
    await estimator(options=options).assign(group)
    penalty = KL_COEF * (DEFAULT_LOGPROB - FROZEN_LOGPROB)
    expected = expected_call_advantages(runs=first_item_group)
    for call, values in action_advantages(group=group).items():
        assert values == {round(expected.get(call, 0.0) - penalty, 4)}


async def test_a_group_above_max_kl_stops_the_run(first_item_group: list[EpisodeRun]) -> None:
    base = PolicyView(id="base", scorer=frozen_scores)
    log_ratio = torch.tensor(FROZEN_LOGPROB - DEFAULT_LOGPROB)
    k3 = float(torch.exp(log_ratio) - log_ratio - 1.0)
    below = {"kl_policy": "base", "kl_coef": KL_COEF, "max_kl": k3 + 0.01}
    group = credit_group(runs=first_item_group, task_id=TASK_ID, policies={"base": base})
    await estimator(options=below).assign(group)
    above = {"kl_policy": "base", "kl_coef": KL_COEF, "max_kl": k3 - 0.01}
    group = credit_group(runs=first_item_group, task_id=TASK_ID, policies={"base": base})
    with pytest.raises(KlLimitExceeded):
        await estimator(options=above).assign(group)


def check_context(*, policies: dict[str, Any]) -> CreditCheckContext:
    """A load-time check's context over a config with ``policies`` and a trained Qwen3.8-27B."""
    config = SimpleNamespace(
        policies=policies, train=SimpleNamespace(model_name="Qwen/Qwen3.8-27B")
    )
    return CreditCheckContext(entry="signal-game", policies=(MAIN, *policies), config=config)


def test_the_check_refuses_a_kl_policy_that_is_missing_trained_or_another_model() -> None:
    options = RoundBaselineOptions(kl_policy="base", kl_coef=0.02, max_kl=0.3)
    frozen = SimpleNamespace(model_name="Qwen/Qwen3.8-27B", trainable=False)
    RoundBaseline.check(options, check_context(policies={"base": frozen}))
    with pytest.raises(ValueError, match="not a policy"):
        RoundBaseline.check(options, check_context(policies={}))
    trained = SimpleNamespace(model_name="Qwen/Qwen3.8-27B", trainable=True)
    with pytest.raises(ValueError, match="must be frozen"):
        RoundBaseline.check(options, check_context(policies={"base": trained}))
    other = SimpleNamespace(model_name="Qwen/Qwen3-32B", trainable=False)
    with pytest.raises(ValueError, match="another model"):
        RoundBaseline.check(options, check_context(policies={"base": other}))
    coefficient_alone = RoundBaselineOptions(kl_policy=None, kl_coef=0.02, max_kl=None)
    with pytest.raises(ValueError, match="kl_coef must be 0"):
        RoundBaseline.check(coefficient_alone, check_context(policies={}))
