"""Message entropy metric: within-message character Shannon entropy.

Scores every primary-channel message by the Shannon entropy of its character
distribution (``-Σ p(c)·log2 p(c)``, in bits/char) and reports the mean per
round and overall. Model-free and deterministic: it needs no language model or
corpus, and does not consult the LLM provider.

Unlike ``perplexity`` (GPT-2 per token) and ``english_ngram_surprisal`` (English
char trigram per char), this measures intrinsic symbol diversity / compressibility:
degenerate repetition collapses toward 0 (``LLLLLLL`` → 0.000) while diverse text
approaches the log2 of the alphabet size. **Lower = more repetitive/compressible.**

Scores the **pristine** text the sender composed (resolved via the ``message_id``
link), not the channel-delivered text, so noise transforms do not contaminate it.
"""

import logging
from pathlib import Path

from glossogen.evaluation.metric_core.character_entropy import character_entropy_bits
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
        scenario: ScenarioBase,
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

        return await measure_primary_channel_message_scores(
            metric_name=self.name,
            channels=channels,
            events=events,
            scenario=scenario,
            load_scorer=_load_entropy_scorer,
            wording=MessageScoreWording(
                score_unit="bits/char",
                measure="within-message character entropy",
                value_unit="bits/char",
                interpretation="lower = more repetitive/compressible",
            ),
        )


def _load_entropy_scorer() -> MessageScorer:
    """Return the character-entropy scorer; it needs nothing loaded."""
    return _score_entropies


def _score_entropies(texts: list[str]) -> list[float]:
    """Character Shannon entropy in bits/char of each text."""
    return [character_entropy_bits(text=text) for text in texts]
