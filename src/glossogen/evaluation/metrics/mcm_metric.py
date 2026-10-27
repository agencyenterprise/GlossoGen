"""Mean Chars per Message (MCM) metric for primary-channel messages.

Computes the mean number of characters per message sent on the scenario's
primary channel. Aggregates per-round and overall statistics. Deterministic:
does not consult the LLM provider.

Pairs with ``mean_chars_per_round``: MCR includes both message length and the
number of messages in a round. MCM instead uses each message as one observation
and reports its mean character length.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metric_core.mean_and_std import mean, population_std
from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.primary_channel_messages import (
    RoundMessages,
    collect_primary_messages_by_round,
    transmitted_text,
)
from glossogen.evaluation.metric_core.scored_channels import scored_channel_ids
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_base import ScenarioBase

logger = logging.getLogger(__name__)


class RoundMCM(NamedTuple):
    """Per-round aggregate of mean character count across primary-channel messages."""

    round_number: int
    mean_chars: float
    std_chars: float
    message_count: int


class MCMMetric(Metric):
    """Reports per-round mean chars-per-message of primary-channel messages.

    Counts characters in each primary-channel message and averages. The
    headline ``score`` is the overall mean chars/message across the run
    (flattened, not mean of round means). Scenarios without a primary
    channel get a no-op result.
    """

    name = "mean_chars_per_message"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score primary-channel messages and report per-round char-count stats."""
        _ = agent_configs, llm_provider, run_dir, options
        channels = scenario.get_primary_channels()
        if not channels:
            logger.info("%s: skipping — scenario has no primary channel", self.name)
            return []

        measurements: list[Measurement] = []
        for channel in channels:
            rounds = collect_primary_messages_by_round(
                events=events,
                channel_ids=scored_channel_ids(primary=channel, scenario=scenario, events=events),
                text_of=transmitted_text,
            )
            if not rounds:
                logger.info(
                    "%s: skipping — no messages on primary channel %r",
                    self.name,
                    channel.channel_id,
                )
                continue

            round_mcms = [_score_round(round_messages=rm) for rm in rounds]

            all_char_counts = [
                float(len(text)) for round_messages in rounds for text in round_messages.texts
            ]
            total_messages = len(all_char_counts)
            overall_mean = mean(values=all_char_counts)
            overall_std = population_std(values=all_char_counts, value_mean=overall_mean)

            per_round = [
                RoundObservation(
                    round_number=rm.round_number,
                    value=rm.mean_chars,
                    note=f"{rm.message_count} messages, std={rm.std_chars:.2f}",
                )
                for rm in round_mcms
            ]
            summary = (
                f"{total_messages} messages on {channel.channel_id} across "
                f"{len(round_mcms)} rounds; mean {overall_mean:.2f} chars/message "
                f"(std {overall_std:.2f})"
            )

            logger.info(
                "mcm metric: channel=%s %.2f chars/msg over %d msgs in %d rounds",
                channel.channel_id,
                overall_mean,
                total_messages,
                len(round_mcms),
            )
            measurements.append(
                Measurement(
                    metric_name=channel.metric_name(self.name),
                    score=overall_mean,
                    score_unit="chars/message",
                    summary=summary,
                    per_round=per_round,
                    per_agent=[],
                )
            )
        return measurements


def _score_round(round_messages: RoundMessages) -> RoundMCM:
    """Aggregate char counts for a round's messages into a RoundMCM."""
    counts = [float(len(text)) for text in round_messages.texts]
    mean_chars = mean(values=counts)
    std_chars = population_std(values=counts, value_mean=mean_chars)
    return RoundMCM(
        round_number=round_messages.round_number,
        mean_chars=mean_chars,
        std_chars=std_chars,
        message_count=len(counts),
    )
