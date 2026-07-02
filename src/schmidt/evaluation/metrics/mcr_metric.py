"""Mean Chars per Round (MCR) metric for primary-channel messages.

Computes the total number of characters sent on the scenario's primary
channel each round, then averages across rounds. Deterministic — does not
consult the LLM provider.

Captures channel utilization — how much of the per-round character budget
agents actually use.
"""

import logging
import math
from pathlib import Path
from typing import NamedTuple

from schmidt.evaluation.metric_core.measurement import Measurement, RoundObservation
from schmidt.evaluation.metric_core.metric_protocol import Metric
from schmidt.evaluation.metric_core.metric_run_options import MetricRunOptions
from schmidt.llm.provider import LLMProvider
from schmidt.models.agent_config import AgentConfig
from schmidt.models.event import MessageSent, SimulationEvent
from schmidt.scenario_protocol import SimulationScenario

logger = logging.getLogger(__name__)


class RoundCharCount(NamedTuple):
    """Per-round total character count across primary-channel messages."""

    round_number: int
    total_chars: int
    message_count: int


class MCRMetric(Metric):
    """Reports per-round total chars and overall mean chars-per-round.

    Sums the character lengths of all primary-channel messages in each
    round. The headline ``score`` is the mean of those round totals.
    Scenarios without a primary channel get a no-op result.
    """

    name = "mean_chars_per_round"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: SimulationScenario,
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
                primary_channel_id=channel.channel_id,
            )
            if not round_counts:
                logger.info(
                    "%s: skipping — no messages on primary channel %r",
                    self.name,
                    channel.channel_id,
                )
                continue

            per_round_totals = [float(rc.total_chars) for rc in round_counts]
            total_chars = sum(rc.total_chars for rc in round_counts)
            overall_mean = _mean(values=per_round_totals)
            overall_std = _std(values=per_round_totals, mean=overall_mean)

            per_round = [
                RoundObservation(
                    round_number=rc.round_number,
                    value=float(rc.total_chars),
                    note=f"{rc.message_count} messages",
                )
                for rc in round_counts
            ]
            summary = (
                f"{len(round_counts)} rounds with messages on {channel.channel_id}; "
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
    primary_channel_id: str,
) -> list[RoundCharCount]:
    """Sum chars and count messages per round on the primary channel."""
    chars_by_round: dict[int, int] = {}
    messages_by_round: dict[int, int] = {}
    for event in events:
        if not isinstance(event, MessageSent):
            continue
        if event.message.channel_id != primary_channel_id:
            continue
        text = event.message.text
        if not text:
            continue
        chars_by_round[event.round_number] = chars_by_round.get(event.round_number, 0) + len(text)
        messages_by_round[event.round_number] = messages_by_round.get(event.round_number, 0) + 1
    return [
        RoundCharCount(
            round_number=rn,
            total_chars=chars_by_round[rn],
            message_count=messages_by_round[rn],
        )
        for rn in sorted(chars_by_round.keys())
    ]


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
