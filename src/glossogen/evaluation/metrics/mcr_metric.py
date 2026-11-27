"""Mean Chars per Round (MCR) metric for primary-channel messages.

Computes the total size of the messages sent on the scenario's primary
channel each round, including zero for silent rounds, then averages across
rounds. A message's size is its characters, or its painted pixels when the
channel carries drawings, and the score's unit says which. Deterministic: it
does not consult the LLM provider.

Captures channel utilization: how much of the per-round budget agents actually
use.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metric_core.mean_and_std import mean, population_std
from glossogen.evaluation.metric_core.primary_channel_messages import (
    collect_message_sizes_by_round,
)
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.measurement import Measurement, RoundObservation
from glossogen.scenario_contract.metric_protocol import Metric
from glossogen.scenario_contract.metric_run_options import MetricRunOptions
from glossogen.scenario_contract.scenario_base import ScenarioBase
from glossogen.scenario_contract.scored_channels import scored_channel_ids

logger = logging.getLogger(__name__)


class RoundTotal(NamedTuple):
    """Per-round total size of the primary-channel messages."""

    round_number: int
    total: int
    message_count: int


class RoundTotals(NamedTuple):
    """Every round's total, and the unit of the summed sizes: ``chars`` or ``pixels``."""

    unit: str
    rounds: list[RoundTotal]


class MCRMetric(Metric):
    """Reports per-round total size and the overall mean size per round.

    Sums the sizes of all primary-channel messages in each round: characters,
    or painted pixels for drawings. The headline ``score`` is the mean of those
    round totals, including zero for a round with no primary-channel message.
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
        """Score primary-channel messages and report per-round size stats."""
        _ = agent_configs, llm_provider, run_dir, options
        channels = scenario.get_primary_channels()
        if not channels:
            logger.info("%s: skipping — scenario has no primary channel", self.name)
            return []

        measurements: list[Measurement] = []
        for channel in channels:
            totals = _collect_round_totals(
                events=events,
                channel_ids=scored_channel_ids(primary=channel, scenario=scenario, events=events),
            )
            round_counts = totals.rounds
            unit = totals.unit
            if not round_counts:
                logger.info(
                    "%s: skipping — run contains no rounds for primary channel %r",
                    self.name,
                    channel.channel_id,
                )
                continue

            per_round_totals = [float(rc.total) for rc in round_counts]
            run_total = sum(rc.total for rc in round_counts)
            overall_mean = mean(values=per_round_totals)
            overall_std = population_std(values=per_round_totals, value_mean=overall_mean)

            per_round = [
                RoundObservation(
                    round_number=rc.round_number,
                    value=float(rc.total),
                    note=f"{rc.message_count} messages",
                )
                for rc in round_counts
            ]
            summary = (
                f"{len(round_counts)} rounds on {channel.channel_id}; "
                f"{run_total} total {unit}, mean {overall_mean:.1f} {unit}/round "
                f"(std {overall_std:.1f})"
            )

            logger.info(
                "mcr metric: channel=%s %.1f %s/round over %d rounds (%d total %s)",
                channel.channel_id,
                overall_mean,
                unit,
                len(round_counts),
                run_total,
                unit,
            )
            measurements.append(
                Measurement(
                    metric_name=channel.metric_name(self.name),
                    score=overall_mean,
                    score_unit=f"{unit}/round",
                    summary=summary,
                    per_round=per_round,
                    per_agent=[],
                )
            )
        return measurements


def _collect_round_totals(
    events: list[SimulationEvent],
    channel_ids: frozenset[str],
) -> RoundTotals:
    """Sum primary-channel message sizes for every round represented in the log."""
    message_sizes = collect_message_sizes_by_round(events=events, channel_ids=channel_ids)
    sizes_by_round = {
        round_sizes.round_number: round_sizes.sizes for round_sizes in message_sizes.rounds
    }
    round_numbers = {event.round_number for event in events if event.round_number > 0}
    round_numbers.update(sizes_by_round.keys())
    round_counts: list[RoundTotal] = []
    for rn in sorted(round_numbers):
        sizes = sizes_by_round.get(rn, [])
        round_counts.append(RoundTotal(round_number=rn, total=sum(sizes), message_count=len(sizes)))
    return RoundTotals(unit=message_sizes.unit, rounds=round_counts)
