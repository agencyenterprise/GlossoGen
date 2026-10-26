"""Mean per-message score of each primary channel, by round and over the run.

Metrics that score each primary-channel message on its own (surprisal, entropy,
compressibility) supply a loader for their scorer and the words their
measurement uses. This module scores the pristine text of every message on each
primary channel, drops scores that come back NaN, averages them per round and
then across rounds, and builds one ``Measurement`` per channel that carried
messages.
"""

import asyncio
import logging
import math
from collections.abc import Callable
from typing import NamedTuple, Protocol

from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.primary_channel_messages import (
    RoundMessages,
    collect_primary_messages_by_round,
)
from glossogen.evaluation.metric_core.pristine_text_index import build_pristine_text_index
from glossogen.evaluation.metric_core.scored_channels import scored_channel_ids
from glossogen.evaluation.metric_core.surprisal_stats import mean, population_std
from glossogen.models.event import SimulationEvent
from glossogen.scenario_base import PrimaryChannel, ScenarioBase

logger = logging.getLogger(__name__)


class MessageScorer(Protocol):
    """Scores a batch of message texts, one value per text, NaN for an unscorable one."""

    def __call__(self, texts: list[str]) -> list[float]:
        """Return one score per text in ``texts``."""
        ...


class MessageScoreWording(NamedTuple):
    """How a metric names its score in the measurement it reports.

    The summary reads "mean ``measure`` <value> ``value_unit``", followed by a
    parenthetical that opens with ``interpretation`` when it is set.
    """

    score_unit: str
    measure: str
    value_unit: str
    interpretation: str | None


class RoundScore(NamedTuple):
    """Per-round aggregate of the scores of a round's messages."""

    round_number: int
    mean_score: float
    std_score: float
    message_count: int


async def measure_primary_channel_message_scores(
    metric_name: str,
    channels: list[PrimaryChannel],
    events: list[SimulationEvent],
    scenario: ScenarioBase,
    load_scorer: Callable[[], MessageScorer],
    wording: MessageScoreWording,
) -> list[Measurement]:
    """Score each channel in ``channels`` and return its mean-message-score measurement.

    A channel with no messages, or whose every message scores NaN, gets no measurement.

    ``load_scorer`` runs in a worker thread, once per channel with messages. An
    exception it raises propagates: the metric was requested and cannot run, and
    reporting nothing would read as a clean result.
    """
    pristine_index = build_pristine_text_index(events=events)
    measurements: list[Measurement] = []
    for channel in channels:
        rounds = collect_primary_messages_by_round(
            events=events,
            channel_ids=scored_channel_ids(primary=channel, scenario=scenario, events=events),
            pristine_index=pristine_index,
        )
        if not rounds:
            logger.info(
                "%s: skipping — no messages on primary channel %r",
                metric_name,
                channel.channel_id,
            )
            continue

        round_scores = await asyncio.to_thread(
            _score_all_rounds, load_scorer=load_scorer, rounds=rounds
        )
        if not round_scores:
            # Every message scored NaN. A 0.0 would read as a measured value.
            logger.info(
                "%s: skipping — no scorable messages on primary channel %r",
                metric_name,
                channel.channel_id,
            )
            continue

        all_means = [rs.mean_score for rs in round_scores]
        total_messages = sum(rs.message_count for rs in round_scores)
        overall_mean = mean(values=all_means)
        overall_std = population_std(values=all_means, value_mean=overall_mean)

        per_round = [
            RoundObservation(
                round_number=rs.round_number,
                value=rs.mean_score,
                note=f"{rs.message_count} messages, std={rs.std_score:.3f}",
            )
            for rs in round_scores
        ]
        qualifiers: list[str] = []
        if wording.interpretation is not None:
            qualifiers.append(wording.interpretation)
        qualifiers.append(f"round-to-round std {overall_std:.3f}")
        summary = (
            f"{total_messages} messages on {channel.channel_id} across "
            f"{len(round_scores)} rounds; mean {wording.measure} "
            f"{overall_mean:.3f} {wording.value_unit} ({'; '.join(qualifiers)})"
        )
        logger.info(
            "%s: channel=%s rounds=%d messages=%d overall_mean=%.3f",
            metric_name,
            channel.channel_id,
            len(round_scores),
            total_messages,
            overall_mean,
        )
        measurements.append(
            Measurement(
                metric_name=channel.metric_name(metric_name),
                score=overall_mean,
                score_unit=wording.score_unit,
                summary=summary,
                per_round=per_round,
                per_agent=[],
            )
        )
    return measurements


def _score_all_rounds(
    load_scorer: Callable[[], MessageScorer], rounds: list[RoundMessages]
) -> list[RoundScore]:
    """Load the scorer once and produce a RoundScore per round with a scorable message.

    NaN scores are dropped: serialized to JSON, NaN becomes ``null``, which fails
    validation downstream.
    """
    score_texts = load_scorer()
    results: list[RoundScore] = []
    for round_messages in rounds:
        scores = [
            score for score in score_texts(texts=round_messages.texts) if not math.isnan(score)
        ]
        if not scores:
            continue
        mean_score = mean(values=scores)
        results.append(
            RoundScore(
                round_number=round_messages.round_number,
                mean_score=mean_score,
                std_score=population_std(values=scores, value_mean=mean_score),
                message_count=len(scores),
            )
        )
    return results
