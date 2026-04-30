"""Perplexity evaluator that scores primary-channel messages with a fixed HF model.

Uses ``minicons.scorer.IncrementalLMScorer`` with ``gpt2`` to compute the mean
per-token surprisal (in nats) of every message sent on the scenario's primary
channel. Aggregates per-round and overall statistics into the result's
evidence. Verdict is always ``PARTIAL`` -- this evaluator reports numbers, not
a classification.
"""

import asyncio
import logging
import math
from pathlib import Path
from typing import Any, NamedTuple

import torch
from minicons import scorer  # type: ignore[import-untyped]

from schmidt.evaluation.evaluation_report import MetricResult, Verdict
from schmidt.evaluation.evaluator_protocol import Evaluator
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class RoundPerplexity(NamedTuple):
    """Per-round aggregate of mean per-token surprisal across messages."""

    round_number: int
    mean_surprisal: float
    std_surprisal: float
    message_count: int


class RoundMessages(NamedTuple):
    """All primary-channel message texts for a single round."""

    round_number: int
    texts: list[str]


class PerplexityEvaluator(Evaluator):
    """Reports per-round mean per-token surprisal of primary-channel messages.

    Loads ``gpt2-medium`` via minicons, scores each primary-channel message,
    averages per-round, and emits stats as evidence. Returns ``PARTIAL`` with a
    numeric ``score`` equal to the overall mean per-token surprisal in nats.
    Scenarios without a primary channel get a no-op result.
    """

    name = "perplexity"
    model_name = "gpt2"

    async def evaluate(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> MetricResult:
        """Score primary-channel messages and report per-round perplexity stats."""
        _ = agent_configs, llm_provider, run_dir
        primary_channel_id = scenario.get_primary_channel_id()
        if primary_channel_id is None:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.PARTIAL,
                score=0.0,
                evidence=["scenario has no primary channel; perplexity evaluator skipped"],
                per_agent={},
                rounds_identified=[],
            )

        rounds = _collect_primary_messages_by_round(
            events=events,
            primary_channel_id=primary_channel_id,
        )
        if not rounds:
            return MetricResult(
                evaluator_name=self.name,
                verdict=Verdict.PARTIAL,
                score=0.0,
                evidence=[
                    f"no messages found on primary channel {primary_channel_id!r}; "
                    "perplexity evaluator has nothing to score",
                ],
                per_agent={},
                rounds_identified=[],
            )

        round_perplexities = await asyncio.to_thread(
            _score_all_rounds,
            model_name=self.model_name,
            rounds=rounds,
        )

        all_means = [rp.mean_surprisal for rp in round_perplexities]
        total_messages = sum(rp.message_count for rp in round_perplexities)
        overall_mean = _mean(values=all_means)
        overall_std = _std(values=all_means, mean=overall_mean)

        evidence = [
            f"perplexity model: {self.model_name} (primary channel: {primary_channel_id})",
            f"scored {total_messages} messages across {len(round_perplexities)} rounds",
            (
                f"overall mean per-token surprisal: {overall_mean:.3f} nats "
                f"(round-to-round std {overall_std:.3f})"
            ),
        ]
        for rp in round_perplexities:
            evidence.append(
                f"round {rp.round_number}: mean={rp.mean_surprisal:.3f} "
                f"std={rp.std_surprisal:.3f} n={rp.message_count}"
            )

        logger.info(
            "perplexity: model=%s rounds=%d messages=%d overall_mean=%.3f",
            self.model_name,
            len(round_perplexities),
            total_messages,
            overall_mean,
        )
        return MetricResult(
            evaluator_name=self.name,
            verdict=Verdict.PARTIAL,
            score=overall_mean,
            evidence=evidence,
            per_agent={},
            rounds_identified=[],
        )


def _collect_primary_messages_by_round(
    events: list[SimulationEvent],
    primary_channel_id: str,
) -> list[RoundMessages]:
    """Extract message texts from MessageSent events on the primary channel, by round."""
    by_round: dict[int, list[str]] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id != primary_channel_id:
            continue
        text = event.message.text
        if not text:
            continue
        if event.round_number not in by_round:
            by_round[event.round_number] = []
        by_round[event.round_number].append(text)
    return [RoundMessages(round_number=rn, texts=by_round[rn]) for rn in sorted(by_round.keys())]


def _score_all_rounds(
    model_name: str,
    rounds: list[RoundMessages],
) -> list[RoundPerplexity]:
    """Load the scorer once and produce a RoundPerplexity for each round."""
    if torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"
    logger.info("perplexity: loading %s on %s", model_name, device)
    lm_scorer = scorer.IncrementalLMScorer(model_name, device)

    results: list[RoundPerplexity] = []
    for round_messages in rounds:
        per_message_surprisals = _score_messages(scorer_obj=lm_scorer, texts=round_messages.texts)
        mean_surprisal = _mean(values=per_message_surprisals)
        std_surprisal = _std(values=per_message_surprisals, mean=mean_surprisal)
        results.append(
            RoundPerplexity(
                round_number=round_messages.round_number,
                mean_surprisal=mean_surprisal,
                std_surprisal=std_surprisal,
                message_count=len(per_message_surprisals),
            )
        )
    return results


def _score_messages(scorer_obj: Any, texts: list[str]) -> list[float]:
    """Return mean per-token surprisal in nats for each input text."""
    scores: list[float] = scorer_obj.sequence_score(
        texts,
        reduction=lambda x: -x.mean(0).item(),
    )
    return [float(s) for s in scores]


def _mean(values: list[float]) -> float:
    """Arithmetic mean; returns 0.0 for an empty list."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _std(values: list[float], mean: float) -> float:
    """Population standard deviation; returns 0.0 for fewer than two values."""
    if len(values) < 2:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)
