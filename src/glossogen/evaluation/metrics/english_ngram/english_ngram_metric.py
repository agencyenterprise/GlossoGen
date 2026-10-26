"""English n-gram surprisal metric: how un-English-like primary-channel text is.

Scores every primary-channel message under a character-level English trigram
(see ``english_ngram_model``) and reports the mean per-character surprisal in
nats, per round and overall. Unlike ``perplexity`` (GPT-2, per subword token),
this rewards English-likeness rather than compressibility: degenerate
repetition (``LLLLLLL``), emergent codes (``Lf Lf``), and digit runs score
**high**, while fluent English scores low. **Higher = less English-like.**

Scores the **pristine** text the sender composed (resolved via the
``message_id`` link) rather than the channel-delivered text, so noise transforms
do not contaminate the signal. Deterministic: it does not consult the LLM provider.
"""

import logging
from pathlib import Path

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.primary_channel_message_scores import (
    MessageScorer,
    MessageScoreWording,
    measure_primary_channel_message_scores,
)
from glossogen.evaluation.metrics.english_ngram.english_ngram_model import (
    load_english_trigram_model,
)
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_base import ScenarioBase

logger = logging.getLogger(__name__)


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
        scenario: ScenarioBase,
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

        # A cold cache with no `datasets` installed raises MetricsMlExtraMissing
        # from the loader, which is left to propagate.
        return await measure_primary_channel_message_scores(
            metric_name=self.name,
            channels=channels,
            events=events,
            scenario=scenario,
            load_scorer=_load_trigram_scorer,
            wording=MessageScoreWording(
                score_unit="nats/char (english-trigram)",
                measure="per-char English-trigram surprisal",
                value_unit="nats",
                interpretation="higher = less English-like",
            ),
        )


def _load_trigram_scorer() -> MessageScorer:
    """Load the English trigram and return a scorer of mean per-character surprisal.

    A message with no scorable characters (e.g. all whitespace) scores NaN.
    """
    model = load_english_trigram_model()

    def score_texts(texts: list[str]) -> list[float]:
        return [model.mean_char_surprisal(text=text) for text in texts]

    return score_texts
