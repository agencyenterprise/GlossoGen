"""Message entropy metric: within-message character Shannon entropy.

Scores every primary-channel message by the Shannon entropy of its character
distribution (``-Σ p(c)·log2 p(c)``, in bits/char) and reports the mean per
round and overall. Model-free and deterministic — needs no language model or
corpus, and does not consult the LLM provider.

Unlike ``perplexity`` (GPT-2 per token) and ``english_ngram_surprisal`` (English
char trigram per char), this measures intrinsic symbol diversity / compressibility:
degenerate repetition collapses toward 0 (``LLLLLLL`` → 0.000) while diverse text
approaches the log2 of the alphabet size. **Lower = more repetitive/compressible.**

Scores the **pristine** text the sender composed (resolved via the ``message_id``
link), not the channel-delivered text, so noise transforms do not contaminate it.
"""

import logging
import math
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metric_core.character_entropy import character_entropy_bits
from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.primary_channel_messages import (
    RoundMessages,
    collect_primary_messages_by_round,
)
from glossogen.evaluation.metric_core.pristine_text_index import build_pristine_text_index
from glossogen.evaluation.metric_core.surprisal_stats import mean, population_std
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class RoundEntropy(NamedTuple):
    """Per-round aggregate of mean per-character entropy across messages."""

    round_number: int
    mean_entropy: float
    std_entropy: float
    message_count: int


class MessageEntropyMetric(Metric):
    """Reports per-round mean within-message character Shannon entropy (bits/char).

    Scores each primary-channel message's character-distribution entropy, averages
    per-round, and emits the overall mean as the headline score. Lower means more
    repetitive/compressible. Scenarios without a primary channel get a no-op result.
    """

    name = "message_entropy"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score primary-channel messages and report per-round entropy stats."""
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

            round_entropies = [_score_round(round_messages=rm) for rm in rounds]
            round_entropies = [re for re in round_entropies if re is not None]

            all_means = [re.mean_entropy for re in round_entropies]
            total_messages = sum(re.message_count for re in round_entropies)
            overall_mean = mean(values=all_means)
            overall_std = population_std(values=all_means, value_mean=overall_mean)

            per_round = [
                RoundObservation(
                    round_number=re.round_number,
                    value=re.mean_entropy,
                    note=f"{re.message_count} messages, std={re.std_entropy:.3f}",
                )
                for re in round_entropies
            ]
            summary = (
                f"{total_messages} messages on {channel.channel_id} across "
                f"{len(round_entropies)} rounds; mean within-message character entropy "
                f"{overall_mean:.3f} bits/char (lower = more repetitive/compressible; "
                f"round-to-round std {overall_std:.3f})"
            )

            logger.info(
                "message_entropy: channel=%s rounds=%d messages=%d overall_mean=%.3f",
                channel.channel_id,
                len(round_entropies),
                total_messages,
                overall_mean,
            )
            measurements.append(
                Measurement(
                    metric_name=channel.metric_name(self.name),
                    score=overall_mean,
                    score_unit="bits/char",
                    summary=summary,
                    per_round=per_round,
                    per_agent=[],
                )
            )
        return measurements


def _score_round(round_messages: RoundMessages) -> RoundEntropy | None:
    """Aggregate per-message character entropy for one round, or None if it had none."""
    per_message = [character_entropy_bits(text=text) for text in round_messages.texts]
    per_message = [value for value in per_message if not math.isnan(value)]
    if not per_message:
        return None
    mean_entropy = mean(values=per_message)
    std_entropy = population_std(values=per_message, value_mean=mean_entropy)
    return RoundEntropy(
        round_number=round_messages.round_number,
        mean_entropy=mean_entropy,
        std_entropy=std_entropy,
        message_count=len(per_message),
    )
