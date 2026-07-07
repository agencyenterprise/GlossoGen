"""Gzip compression ratio metric: per-message DEFLATE compressibility.

Scores every primary-channel message by its raw-DEFLATE compression ratio
(``len(raw_deflate(text)) / len(text)`` in bytes, compressed/original) and reports
the mean per round and overall. DEFLATE is gzip's codec; running it without the
gzip wrapper removes the constant 18-byte header/footer that would otherwise
inflate short-message ratios (see ``gzip_compression``). Model-free and
deterministic — needs no language model or corpus, and does not consult the LLM
provider.

Lower means more compressible/repetitive: DEFLATE exploits repeated substrings and
codes, so a protocol that re-uses the same tokens compresses well. Complements
``message_entropy`` (per-character Shannon entropy) by capturing multi-character
repetition. **Lower = more compressible/repetitive.**

DEFLATE keeps a small per-stream overhead (block header + Huffman framing), so the
very shortest or incompressible messages can read slightly above 1.0; the signal is
most meaningful in aggregate.

Scores the **pristine** text the sender composed (resolved via the ``message_id``
link), not the channel-delivered text, so noise transforms do not contaminate it.
"""

import logging
import math
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metric_core.gzip_compression import gzip_compression_ratio
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


class RoundCompression(NamedTuple):
    """Per-round aggregate of mean gzip compression ratio across messages."""

    round_number: int
    mean_ratio: float
    std_ratio: float
    message_count: int


class GzipCompressionRatioMetric(Metric):
    """Reports per-round mean per-message gzip compression ratio (compressed/original).

    Scores each primary-channel message's gzip ratio, averages per-round, and emits
    the overall mean as the headline score. Lower means more compressible/repetitive.
    Scenarios without a primary channel get a no-op result.
    """

    name = "gzip_compression_ratio"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score primary-channel messages and report per-round compression-ratio stats."""
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

            round_compressions = [_score_round(round_messages=rm) for rm in rounds]
            round_compressions = [rc for rc in round_compressions if rc is not None]

            all_means = [rc.mean_ratio for rc in round_compressions]
            total_messages = sum(rc.message_count for rc in round_compressions)
            overall_mean = mean(values=all_means)
            overall_std = population_std(values=all_means, value_mean=overall_mean)

            per_round = [
                RoundObservation(
                    round_number=rc.round_number,
                    value=rc.mean_ratio,
                    note=f"{rc.message_count} messages, std={rc.std_ratio:.3f}",
                )
                for rc in round_compressions
            ]
            summary = (
                f"{total_messages} messages on {channel.channel_id} across "
                f"{len(round_compressions)} rounds; mean per-message gzip compression ratio "
                f"{overall_mean:.3f} compressed/original (raw DEFLATE, gzip framing excluded; "
                f"lower = more compressible/repetitive; "
                f"round-to-round std {overall_std:.3f})"
            )

            logger.info(
                "gzip_compression_ratio: channel=%s rounds=%d messages=%d overall_mean=%.3f",
                channel.channel_id,
                len(round_compressions),
                total_messages,
                overall_mean,
            )
            measurements.append(
                Measurement(
                    metric_name=channel.metric_name(self.name),
                    score=overall_mean,
                    score_unit="compressed/original",
                    summary=summary,
                    per_round=per_round,
                    per_agent=[],
                )
            )
        return measurements


def _score_round(round_messages: RoundMessages) -> RoundCompression | None:
    """Aggregate per-message gzip compression ratio for one round, or None if it had none."""
    per_message = [gzip_compression_ratio(text=text) for text in round_messages.texts]
    per_message = [value for value in per_message if not math.isnan(value)]
    if not per_message:
        return None
    mean_ratio = mean(values=per_message)
    std_ratio = population_std(values=per_message, value_mean=mean_ratio)
    return RoundCompression(
        round_number=round_messages.round_number,
        mean_ratio=mean_ratio,
        std_ratio=std_ratio,
        message_count=len(per_message),
    )
