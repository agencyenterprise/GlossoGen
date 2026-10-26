"""Gzip compression ratio metric: per-message DEFLATE compressibility.

Scores every primary-channel message by its raw-DEFLATE compression ratio
(``len(raw_deflate(text)) / len(text)`` in bytes, compressed/original) and reports
the mean per round and overall. DEFLATE is gzip's codec; running it without the
gzip wrapper removes the constant 18-byte header/footer that would otherwise
inflate short-message ratios (see ``gzip_compression``). Model-free and
deterministic: it needs no language model or corpus, and does not consult the LLM
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
from pathlib import Path

from glossogen.evaluation.metric_core.gzip_compression import gzip_compression_ratio
from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.primary_channel_message_scores import (
    MessageScorer,
    MessageScoreWording,
    measure_primary_channel_message_scores,
)
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_base import ScenarioBase

logger = logging.getLogger(__name__)


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
        scenario: ScenarioBase,
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

        return await measure_primary_channel_message_scores(
            metric_name=self.name,
            channels=channels,
            events=events,
            scenario=scenario,
            load_scorer=_load_compression_scorer,
            wording=MessageScoreWording(
                score_unit="compressed/original",
                measure="per-message gzip compression ratio",
                value_unit="compressed/original",
                interpretation=(
                    "raw DEFLATE, gzip framing excluded; lower = more compressible/repetitive"
                ),
            ),
        )


def _load_compression_scorer() -> MessageScorer:
    """Return the compression-ratio scorer; it needs nothing loaded."""
    return _score_compression_ratios


def _score_compression_ratios(texts: list[str]) -> list[float]:
    """Raw-DEFLATE compression ratio, compressed/original, of each text."""
    return [gzip_compression_ratio(text=text) for text in texts]
