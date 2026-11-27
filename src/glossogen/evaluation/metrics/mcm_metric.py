"""Mean Chars per Message (MCM) metric for primary-channel messages.

Computes the mean size of the messages sent on the scenario's primary
channel: characters, or painted pixels when the channel carries drawings, and
the score's unit says which. Aggregates per-round and overall statistics.
Deterministic: does not consult the LLM provider.

Pairs with ``mean_chars_per_round``: MCR includes both message length and the
number of messages in a round. MCM instead uses each message as one observation
and reports its mean size.
"""

import logging
from pathlib import Path
from typing import NamedTuple

from glossogen.evaluation.metric_core.mean_and_std import mean, population_std
from glossogen.evaluation.metric_core.primary_channel_messages import (
    RoundMessageSizes,
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


class RoundMCM(NamedTuple):
    """Per-round mean and spread of the primary-channel message sizes."""

    round_number: int
    mean_size: float
    std_size: float
    message_count: int


class MCMMetric(Metric):
    """Reports per-round mean size of primary-channel messages.

    Takes each primary-channel message's size (characters, or painted pixels
    for a drawing) and averages. The headline ``score`` is the overall mean
    size per message across the run
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
        """Score primary-channel messages and report per-round size stats."""
        _ = agent_configs, llm_provider, run_dir, options
        channels = scenario.get_primary_channels()
        if not channels:
            logger.info("%s: skipping — scenario has no primary channel", self.name)
            return []

        measurements: list[Measurement] = []
        for channel in channels:
            message_sizes = collect_message_sizes_by_round(
                events=events,
                channel_ids=scored_channel_ids(primary=channel, scenario=scenario, events=events),
            )
            rounds = message_sizes.rounds
            unit = message_sizes.unit
            if not rounds:
                logger.info(
                    "%s: skipping — no messages on primary channel %r",
                    self.name,
                    channel.channel_id,
                )
                continue

            round_mcms = [_score_round(round_sizes=rs) for rs in rounds]

            all_sizes = [float(size) for round_sizes in rounds for size in round_sizes.sizes]
            total_messages = len(all_sizes)
            overall_mean = mean(values=all_sizes)
            overall_std = population_std(values=all_sizes, value_mean=overall_mean)

            per_round = [
                RoundObservation(
                    round_number=rm.round_number,
                    value=rm.mean_size,
                    note=f"{rm.message_count} messages, std={rm.std_size:.2f}",
                )
                for rm in round_mcms
            ]
            summary = (
                f"{total_messages} messages on {channel.channel_id} across "
                f"{len(round_mcms)} rounds; mean {overall_mean:.2f} {unit}/message "
                f"(std {overall_std:.2f})"
            )

            logger.info(
                "mcm metric: channel=%s %.2f %s/msg over %d msgs in %d rounds",
                channel.channel_id,
                overall_mean,
                unit,
                total_messages,
                len(round_mcms),
            )
            measurements.append(
                Measurement(
                    metric_name=channel.metric_name(self.name),
                    score=overall_mean,
                    score_unit=f"{unit}/message",
                    summary=summary,
                    per_round=per_round,
                    per_agent=[],
                )
            )
        return measurements


def _score_round(round_sizes: RoundMessageSizes) -> RoundMCM:
    """Aggregate a round's message sizes into a RoundMCM."""
    sizes = [float(size) for size in round_sizes.sizes]
    mean_size = mean(values=sizes)
    std_size = population_std(values=sizes, value_mean=mean_size)
    return RoundMCM(
        round_number=round_sizes.round_number,
        mean_size=mean_size,
        std_size=std_size,
        message_count=len(sizes),
    )
