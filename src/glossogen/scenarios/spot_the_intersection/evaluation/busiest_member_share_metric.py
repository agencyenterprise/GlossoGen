"""``busiest_member_share``: how much of a team's count its busiest member sent, round by round.

Each round's value is the busiest member's characters over the team's, both as
charged (until the team's last member submits). With four members, 0.25 means
the team spread its sending evenly and 1.0 means one member sent everything. The
score is the mean over the rounds the team sent anything, and each member's
observation is its share of everything the team sent in the run.
"""

import logging
from pathlib import Path

from glossogen.evaluation.metric_core.measurement import (
    AgentObservation,
    Measurement,
    RoundObservation,
)
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.scenario_base import ScenarioBase
from glossogen.scenarios.spot_the_intersection.evaluation.team_traffic import (
    TeamTraffic,
    team_traffic,
)

logger = logging.getLogger(__name__)


class BusiestMemberShareMetric(Metric):
    """Per team, the busiest member's share of the team's characters in each round."""

    name = "busiest_member_share"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """One measurement per team that was charged for anything."""
        _ = agent_configs, llm_provider, run_dir, options
        measurements: list[Measurement] = []
        for traffic in team_traffic(scenario=scenario, events=events):
            measurement = self._measure(traffic=traffic)
            if measurement is None:
                logger.info(
                    "busiest_member_share: %s was charged for no characters; skipping",
                    traffic.primary.channel_id,
                )
                continue
            measurements.append(measurement)
        return measurements

    def _measure(self, traffic: TeamTraffic) -> Measurement | None:
        """The team's measurement, or ``None`` when it was charged for no characters."""
        per_round = _round_shares(traffic=traffic)
        team_total = sum(message.characters for message in traffic.messages)
        if not per_round or team_total == 0:
            return None
        score = sum(observation.value for observation in per_round) / len(per_round)
        return Measurement(
            metric_name=traffic.primary.metric_name(self.name),
            score=score,
            score_unit="busiest member's share of the team's characters",
            summary=(
                f"the busiest member sent {score:.0%} of the team's characters, "
                f"averaged over {len(per_round)} rounds"
            ),
            per_round=per_round,
            per_agent=_member_shares(traffic=traffic, team_total=team_total),
        )


def _round_shares(traffic: TeamTraffic) -> list[RoundObservation]:
    """The busiest member's share in each round the team sent any characters."""
    by_round: dict[int, dict[str, int]] = {}
    for message in traffic.messages:
        by_agent = by_round.setdefault(message.round_number, {})
        by_agent[message.sender_agent_id] = (
            by_agent.get(message.sender_agent_id, 0) + message.characters
        )
    observations: list[RoundObservation] = []
    for round_number, by_agent in sorted(by_round.items()):
        total = sum(by_agent.values())
        if total == 0:
            continue
        busiest_agent, busiest = max(by_agent.items(), key=lambda item: item[1])
        observations.append(
            RoundObservation(
                round_number=round_number,
                value=busiest / total,
                note=f"{busiest_agent} sent {busiest} of {total} characters",
            )
        )
    return observations


def _member_shares(traffic: TeamTraffic, team_total: int) -> list[AgentObservation]:
    """Each member's share of everything the team sent, silent members included."""
    observations: list[AgentObservation] = []
    for agent_id in traffic.member_agent_ids:
        sent = sum(
            message.characters
            for message in traffic.messages
            if message.sender_agent_id == agent_id
        )
        observations.append(
            AgentObservation(
                agent_id=agent_id,
                value=sent / team_total,
                note=f"{sent} of {team_total} characters",
            )
        )
    return observations
