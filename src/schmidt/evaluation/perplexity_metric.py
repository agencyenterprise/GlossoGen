"""Perplexity metric: mean per-token surprisal of primary-channel messages.

Uses ``minicons.scorer.IncrementalLMScorer`` with ``gpt2`` to compute the mean
per-token surprisal (in nats) of every message sent on the scenario's primary
channel. Produces an overall scalar score plus a per-round breakdown.
Deterministic — does not consult the LLM provider.
"""

import asyncio
import logging
import math
from pathlib import Path
from typing import Any, NamedTuple

import torch
from minicons import scorer  # type: ignore[import-untyped]

from schmidt.evaluation.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
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


class PerplexityMetric(Metric):
    """Reports per-round mean per-token surprisal of primary-channel messages.

    Loads ``gpt2`` via minicons, scores each primary-channel message,
    averages per-round, and emits the overall mean as the headline score
    in nats. Scenarios without a primary channel get a no-op result.
    """

    name = "perplexity"
    model_name = "gpt2"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> list[Measurement]:
        """Score primary-channel messages and report per-round perplexity stats."""
        _ = agent_configs, llm_provider, run_dir
        primary_channel_id = scenario.get_primary_channel_id()
        if primary_channel_id is None:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="nats/token (gpt2)",
                    summary="scenario has no primary channel; perplexity metric skipped",
                    per_round=[],
                    per_agent=[],
                )
            ]

        rounds = _collect_primary_messages_by_round(
            events=events,
            primary_channel_id=primary_channel_id,
        )
        if not rounds:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="nats/token (gpt2)",
                    summary=(
                        f"no messages found on primary channel {primary_channel_id!r}; "
                        "perplexity metric has nothing to score"
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]

        round_perplexities = await asyncio.to_thread(
            _score_all_rounds,
            model_name=self.model_name,
            rounds=rounds,
        )

        all_means = [rp.mean_surprisal for rp in round_perplexities]
        total_messages = sum(rp.message_count for rp in round_perplexities)
        overall_mean = _mean(values=all_means)
        overall_std = _std(values=all_means, mean=overall_mean)

        per_round = [
            RoundObservation(
                round_number=rp.round_number,
                value=rp.mean_surprisal,
                note=f"{rp.message_count} messages, std={rp.std_surprisal:.3f}",
            )
            for rp in round_perplexities
        ]
        summary = (
            f"{total_messages} messages on {primary_channel_id} across "
            f"{len(round_perplexities)} rounds; mean per-token surprisal "
            f"{overall_mean:.3f} nats (round-to-round std {overall_std:.3f})"
        )

        logger.info(
            "perplexity: model=%s rounds=%d messages=%d overall_mean=%.3f",
            self.model_name,
            len(round_perplexities),
            total_messages,
            overall_mean,
        )
        return [
            Measurement(
                metric_name=self.name,
                score=overall_mean,
                score_unit=f"nats/token ({self.model_name})",
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        ]


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
        if not per_message_surprisals:
            continue
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
    """Return mean per-token surprisal in nats for each input text.

    Drops scores that come back as NaN — minicons returns NaN for inputs that
    tokenize to a single token (no left context), and serializing NaN to JSON
    yields ``null`` which fails Pydantic validation downstream.
    """
    raw_scores: list[float] = scorer_obj.sequence_score(
        texts,
        reduction=lambda x: -x.mean(0).item(),
    )
    out: list[float] = []
    for score in raw_scores:
        value = float(score)
        if math.isnan(value):
            continue
        out.append(value)
    return out


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
