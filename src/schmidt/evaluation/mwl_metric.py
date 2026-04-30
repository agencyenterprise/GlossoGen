"""Mean Word Length (MWL) metric for primary-channel messages.

Computes the mean number of characters per whitespace-delimited word across
every message sent on the scenario's primary channel. Aggregates per-round
and overall statistics. Deterministic — does not consult the LLM provider.

Complements the perplexity metric: perplexity captures *how surprising*
each token is, MWL captures *how long the words themselves are*. A
compressed or coded protocol typically pushes perplexity up and MWL down
(short codes replacing long words).
"""

import logging
import math
from pathlib import Path
from typing import NamedTuple

from schmidt.evaluation.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_protocol import Metric
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class RoundMWL(NamedTuple):
    """Per-round aggregate of mean word-length across primary-channel messages."""

    round_number: int
    mean_chars_per_word: float
    std_chars_per_word: float
    word_count: int


class RoundMessages(NamedTuple):
    """All primary-channel message texts for a single round."""

    round_number: int
    texts: list[str]


class MWLMetric(Metric):
    """Reports per-round mean characters-per-word of primary-channel messages.

    Splits each primary-channel message on whitespace, measures each word's
    length in characters, and averages across all words. The headline
    ``score`` is the overall mean chars/word across the run (flattened over
    all words, not mean of round means). Scenarios without a primary channel
    get a no-op result.
    """

    name = "mean_word_length"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
    ) -> list[Measurement]:
        """Score primary-channel messages and report per-round chars/word stats."""
        _ = agent_configs, llm_provider, run_dir
        primary_channel_id = scenario.get_primary_channel_id()
        if primary_channel_id is None:
            return [
                Measurement(
                    metric_name=self.name,
                    score=0.0,
                    score_unit="chars/word",
                    summary="scenario has no primary channel; mwl metric skipped",
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
                    score_unit="chars/word",
                    summary=(
                        f"no messages found on primary channel {primary_channel_id!r}; "
                        "mwl metric has nothing to score"
                    ),
                    per_round=[],
                    per_agent=[],
                )
            ]

        round_mwls = [_score_round(round_messages=rm) for rm in rounds]

        all_word_lengths = [
            float(len(word))
            for round_messages in rounds
            for text in round_messages.texts
            for word in text.split()
        ]
        total_words = len(all_word_lengths)
        overall_mean = _mean(values=all_word_lengths)
        overall_std = _std(values=all_word_lengths, mean=overall_mean)

        per_round = [
            RoundObservation(
                round_number=rm.round_number,
                value=rm.mean_chars_per_word,
                note=f"{rm.word_count} words, std={rm.std_chars_per_word:.2f}",
            )
            for rm in round_mwls
        ]
        summary = (
            f"{total_words} words on {primary_channel_id} across "
            f"{len(round_mwls)} rounds; mean {overall_mean:.2f} chars/word "
            f"(std {overall_std:.2f})"
        )

        logger.info(
            "mwl metric: %.2f chars/word over %d words in %d rounds",
            overall_mean,
            total_words,
            len(round_mwls),
        )
        return [
            Measurement(
                metric_name=self.name,
                score=overall_mean,
                score_unit="chars/word",
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


def _score_round(round_messages: RoundMessages) -> RoundMWL:
    """Aggregate per-word character counts for a round into a RoundMWL."""
    word_lengths = [float(len(word)) for text in round_messages.texts for word in text.split()]
    mean_chars = _mean(values=word_lengths)
    std_chars = _std(values=word_lengths, mean=mean_chars)
    return RoundMWL(
        round_number=round_messages.round_number,
        mean_chars_per_word=mean_chars,
        std_chars_per_word=std_chars,
        word_count=len(word_lengths),
    )


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
