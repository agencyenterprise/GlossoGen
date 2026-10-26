"""Perplexity metric: mean per-token surprisal of primary-channel messages.

Uses ``minicons.scorer.IncrementalLMScorer`` with ``gpt2`` to compute the mean
per-token surprisal (in nats) of every message sent on the scenario's primary
channel. Produces an overall scalar score plus a per-round breakdown.
Deterministic: it does not consult the LLM provider.

Scores the **pristine** text the sender composed, not what the channel
delivered: when a scenario transforms outgoing messages (e.g. veyru channel
noise replaces dropped characters with ``_``), each primary-channel
``MessageSent`` is resolved back to its pre-transform text via the
``message_id`` link. Runs with no transform (or predating that link) score the
transmitted text unchanged.
"""

import logging
from pathlib import Path
from typing import Any

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.optional_ml_backend import (
    load_incremental_lm_scorer,
    require_perplexity_backend,
    resolve_torch_device,
)
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

_MODEL_NAME = "gpt2"


class PerplexityMetric(Metric):
    """Reports per-round mean per-token surprisal of primary-channel messages.

    Loads ``gpt2`` via minicons, scores each primary-channel message,
    averages per-round, and emits the overall mean as the headline score
    in nats. Scenarios without a primary channel get a no-op result.
    """

    name = "perplexity"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score each primary channel's messages and report per-round perplexity stats."""
        _ = agent_configs, llm_provider, run_dir, options
        # Applicability first: a scenario with no primary channel has nothing to
        # score regardless of which packages are installed, and demanding a
        # multi-gigabyte extra just to report that would be perverse.
        channels = scenario.get_primary_channels()
        if not channels:
            logger.info("%s: skipping — scenario has no primary channel", self.name)
            return []

        # Then dependencies. Raises rather than skipping: an empty result would
        # be indistinguishable from a run with nothing to measure, hiding a
        # broken environment behind a green evaluation.
        require_perplexity_backend(metric_name=self.name)

        return await measure_primary_channel_message_scores(
            metric_name=self.name,
            channels=channels,
            events=events,
            scenario=scenario,
            load_scorer=_load_gpt2_scorer,
            wording=MessageScoreWording(
                score_unit=f"nats/token ({_MODEL_NAME})",
                measure="per-token surprisal",
                value_unit="nats",
                interpretation=None,
            ),
        )


def _load_gpt2_scorer() -> MessageScorer:
    """Load gpt2 and return a scorer of mean per-token surprisal in nats per text.

    Callers must confirm the perplexity backend is installed before invoking this.
    Minicons returns NaN for inputs that tokenize to a single token (no left context).
    """
    device = resolve_torch_device()
    logger.info("perplexity: loading %s on %s", _MODEL_NAME, device)
    incremental_lm_scorer = load_incremental_lm_scorer()
    lm_scorer: Any = incremental_lm_scorer(_MODEL_NAME, device)

    # minicons.IncrementalLMScorer is untyped; ``reduction`` is called with a
    # torch.Tensor whose ``.mean(0).item()`` is a float.
    def _negative_mean(tensor: Any) -> float:
        return -tensor.mean(0).item()

    def score_texts(texts: list[str]) -> list[float]:
        raw_scores: list[float] = lm_scorer.sequence_score(texts, reduction=_negative_mean)
        return [float(score) for score in raw_scores]

    return score_texts
