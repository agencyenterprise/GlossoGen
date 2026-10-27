"""Mean Chars per Round (MCR) metric for primary-channel messages.

Computes the total number of characters sent on the scenario's primary
channel each round, including zero for silent rounds, then averages across
rounds. Deterministic: it does not consult the LLM provider.

Captures channel utilization: how much of the per-round character budget
agents actually use.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metric_core.mean_and_std import mean, population_std
from glossogen.evaluation.metric_core.measurement import Measurement, RoundObservation
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.evaluation.metric_core.primary_channel_messages import (
    collect_primary_messages_by_round,
    transmitted_text,
)
from glossogen.evaluation.metric_core.scored_channels import scored_channel_ids
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_base import ScenarioBase

logger = logging.getLogger(__name__)


class RoundCharCount(NamedTuple):
    """Per-round total character count across primary-channel messages."""

    round_number: int
    total_chars: int
    message_count: int


class MCRMetric(Metric):
    """Reports per-round total chars and overall mean chars-per-round.

    Sums the character lengths of all primary-channel messages in each
    round. The headline ``score`` is the mean of those round totals, including
    zero for a round with no primary-channel message.
    Scenarios without a primary channel get a no-op result.
    """

    name = "mean_chars_per_round"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """Score primary-channel messages and report per-round chars stats."""
        _ = agent_configs, llm_provider, run_dir, options
        channels = scenario.get_primary_channels()
        if not channels:
            logger.info("%s: skipping — scenario has no primary channel", self.name)
            return []

        measurements: list[Measurement] = []
        for channel in channels:
            round_counts = _collect_round_char_counts(
                events=events,
                channel_ids=scored_channel_ids(primary=channel, scenario=scenario, events=events),
            )
            if not round_counts:
                logger.info(
                    "%s: skipping — run contains no rounds for primary channel %r",
                    self.name,
                    channel.channel_id,
                )
                continue

            per_round_totals = [float(rc.total_chars) for rc in round_counts]
            total_chars = sum(rc.total_chars for rc in round_counts)
            overall_mean = mean(values=per_round_totals)
            overall_std = population_std(values=per_round_totals, value_mean=overall_mean)

            per_round = [
                RoundObservation(
                    round_number=rc.round_number,
                    value=float(rc.total_chars),
                    note=f"{rc.message_count} messages",
                )
                for rc in round_counts
            ]
            summary = (
                f"{len(round_counts)} rounds on {channel.channel_id}; "
                f"{total_chars} total chars, mean {overall_mean:.1f} chars/round "
                f"(std {overall_std:.1f})"
            )

            logger.info(
                "mcr metric: channel=%s %.1f chars/round over %d rounds (%d total chars)",
                channel.channel_id,
                overall_mean,
                len(round_counts),
                total_chars,
            )
            measurements.append(
                Measurement(
                    metric_name=channel.metric_name(self.name),
                    score=overall_mean,
                    score_unit="chars/round",
                    summary=summary,
                    per_round=per_round,
                    per_agent=[],
                )
            )
        return measurements


def _collect_round_char_counts(
    events: list[SimulationEvent],
    channel_ids: frozenset[str],
) -> list[RoundCharCount]:
    """Sum primary-channel characters for every round represented in the log."""
    texts_by_round = {
        round_messages.round_number: round_messages.texts
        for round_messages in collect_primary_messages_by_round(
            events=events, channel_ids=channel_ids, text_of=transmitted_text
        )
    }
    round_numbers = {event.round_number for event in events if event.round_number > 0}
    round_numbers.update(texts_by_round.keys())
    round_counts: list[RoundCharCount] = []
    for rn in sorted(round_numbers):
        texts = texts_by_round.get(rn, [])
        round_counts.append(
            RoundCharCount(
                round_number=rn,
                total_chars=sum(len(text) for text in texts),
                message_count=len(texts),
            )
        )
    return round_counts
