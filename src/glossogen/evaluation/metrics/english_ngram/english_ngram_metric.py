"""English n-gram surprisal metric: how un-English-like primary-channel text is.

Scores every primary-channel message under a character-level English trigram
(see ``english_ngram_model``) and reports the mean per-character surprisal in
nats, per round and overall. Unlike ``perplexity`` (GPT-2, per subword token),
this rewards English-likeness rather than compressibility: degenerate
repetition (``LLLLLLL``), emergent codes (``Lf Lf``), and digit runs score
**high**, while fluent English scores low. **Higher = less English-like.**

Scores the **pristine** text the sender composed (resolved via the
``message_id`` link) rather than the channel-delivered text, so noise transforms
do not contaminate the signal. Deterministic — does not consult the LLM provider.
"""

import asyncio
import logging
import math
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.primary_channel_messages import (
    RoundMessages,
    collect_primary_messages_by_round,
)
from glossogen.evaluation.metric_core.pristine_text_index import build_pristine_text_index
from glossogen.evaluation.metric_core.surprisal_stats import mean, population_std
from glossogen.evaluation.metrics.english_ngram.english_ngram_model import (
    EnglishTrigramModel,
    load_english_trigram_model,
)
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class RoundSurprisal(NamedTuple):
    """Per-round aggregate of mean per-character surprisal across messages."""

    round_number: int
    mean_surprisal: float
    std_surprisal: float
    message_count: int


class EnglishNgramSurprisalMetric(Metric):
    """Reports per-round mean per-character English-trigram surprisal.

    Loads the cached English character trigram, scores each primary-channel
    message, averages per-round, and emits the overall mean as the headline
    score in nats per character. Higher means less English-like. Scenarios
    without a primary channel get a no-op result.
    """

    name = "english_ngram_surprisal"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score primary-channel messages and report per-round surprisal stats."""
        _ = agent_configs, llm_provider, run_dir, options
        channels = scenario.get_primary_channels()
        if not channels:
            logger.info("%s: skipping — scenario has no primary channel", self.name)
            return []

        pristine_index = build_pristine_text_index(events=events)
        measurements: list[Measurement] = []
        for channel in channels:
            rounds = collect_primary_messages_by_round(
                events=events,
                primary_channel_id=channel.channel_id,
                pristine_index=pristine_index,
            )
            if not rounds:
                logger.info(
                    "%s: skipping — no messages on primary channel %r",
                    self.name,
                    channel.channel_id,
                )
                continue

            round_surprisals = await asyncio.to_thread(_score_all_rounds, rounds=rounds)

            all_means = [rs.mean_surprisal for rs in round_surprisals]
            total_messages = sum(rs.message_count for rs in round_surprisals)
            overall_mean = mean(values=all_means)
            overall_std = population_std(values=all_means, value_mean=overall_mean)

            per_round = [
                RoundObservation(
                    round_number=rs.round_number,
                    value=rs.mean_surprisal,
                    note=f"{rs.message_count} messages, std={rs.std_surprisal:.3f}",
                )
                for rs in round_surprisals
            ]
            summary = (
                f"{total_messages} messages on {channel.channel_id} across "
                f"{len(round_surprisals)} rounds; mean per-char English-trigram "
                f"surprisal {overall_mean:.3f} nats (higher = less English-like; "
                f"round-to-round std {overall_std:.3f})"
            )

            logger.info(
                "english_ngram_surprisal: channel=%s rounds=%d messages=%d overall_mean=%.3f",
                channel.channel_id,
                len(round_surprisals),
                total_messages,
                overall_mean,
            )
            measurements.append(
                Measurement(
                    metric_name=channel.metric_name(self.name),
                    score=overall_mean,
                    score_unit="nats/char (english-trigram)",
                    summary=summary,
                    per_round=per_round,
                    per_agent=[],
                )
            )
        return measurements


def _score_all_rounds(rounds: list[RoundMessages]) -> list[RoundSurprisal]:
    """Load the trigram model once and produce a RoundSurprisal for each round."""
    model = load_english_trigram_model()
    results: list[RoundSurprisal] = []
    for round_messages in rounds:
        per_message_surprisals = _score_messages(model=model, texts=round_messages.texts)
        if not per_message_surprisals:
            continue
        mean_surprisal = mean(values=per_message_surprisals)
        std_surprisal = population_std(values=per_message_surprisals, value_mean=mean_surprisal)
        results.append(
            RoundSurprisal(
                round_number=round_messages.round_number,
                mean_surprisal=mean_surprisal,
                std_surprisal=std_surprisal,
                message_count=len(per_message_surprisals),
            )
        )
    return results


def _score_messages(model: EnglishTrigramModel, texts: list[str]) -> list[float]:
    """Return mean per-character surprisal in nats for each input text.

    Drops scores that come back as NaN — a message with no scorable characters
    (e.g. all whitespace) yields NaN, and serializing NaN to JSON yields
    ``null`` which fails Pydantic validation downstream.
    """
    out: list[float] = []
    for text in texts:
        value = model.mean_char_surprisal(text=text)
        if math.isnan(value):
            continue
        out.append(value)
    return out
