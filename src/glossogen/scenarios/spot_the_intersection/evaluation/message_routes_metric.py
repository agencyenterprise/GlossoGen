"""``message_routes``: how many sender-to-teammate routes a team's messages took each round.

A route is one member reaching one teammate. A post on the team's link reaches
every teammate, and a direct message reaches the teammate it was sent to. Each
round's value counts the distinct routes the team used while it was charged; with
four members there are twelve. A team that broadcasts from every member uses all
twelve, and a relay chain uses few. Each member's observation is the mean number
of teammates it reached per round.
"""

import logging
from pathlib import Path

from glossogen.llm.provider import LLMProvider
from glossogen.models.agent_config import AgentConfig
from glossogen.models.event import ChannelCreated, SimulationEvent
from glossogen.scenario_contract.measurement import (
    AgentObservation,
    Measurement,
    RoundObservation,
)
from glossogen.scenario_contract.metric_protocol import Metric
from glossogen.scenario_contract.metric_run_options import MetricRunOptions
from glossogen.scenario_contract.scenario_base import ScenarioBase
from glossogen.scenarios.spot_the_intersection.evaluation.team_traffic import (
    TeamTraffic,
    team_traffic,
)

logger = logging.getLogger(__name__)

Route = tuple[str, str]


class MessageRoutesMetric(Metric):
    """Per team, the distinct sender-to-teammate routes its messages took each round."""

    name = "message_routes"

    async def compute(
        self,
        events: list[SimulationEvent],
        agent_configs: list[AgentConfig],
        scenario: ScenarioBase,
        llm_provider: LLMProvider,
        run_dir: Path,
        options: MetricRunOptions,
    ) -> list[Measurement]:
        """One measurement per team that was charged for a message."""
        _ = agent_configs, llm_provider, run_dir, options
        members_by_channel = {
            event.channel_id: tuple(event.member_agent_ids)
            for event in events
            if isinstance(event, ChannelCreated)
        }
        measurements: list[Measurement] = []
        for traffic in team_traffic(scenario=scenario, events=events):
            routes_by_round = _routes_by_round(
                traffic=traffic, members_by_channel=members_by_channel
            )
            if not routes_by_round:
                logger.info(
                    "message_routes: %s was charged for no messages; skipping",
                    traffic.primary.channel_id,
                )
                continue
            measurements.append(self._measure(traffic=traffic, routes_by_round=routes_by_round))
        return measurements

    def _measure(self, traffic: TeamTraffic, routes_by_round: dict[int, set[Route]]) -> Measurement:
        """The team's measurement over the rounds it sent anything."""
        per_round = [
            RoundObservation(
                round_number=round_number,
                value=float(len(routes)),
                note=", ".join(f"{sender}→{recipient}" for sender, recipient in sorted(routes)),
            )
            for round_number, routes in sorted(routes_by_round.items())
        ]
        score = sum(observation.value for observation in per_round) / len(per_round)
        return Measurement(
            metric_name=traffic.primary.metric_name(self.name),
            score=score,
            score_unit="distinct sender-to-teammate routes per round",
            summary=f"{score:.1f} routes per round over {len(per_round)} rounds",
            per_round=per_round,
            per_agent=_teammates_reached(traffic=traffic, routes_by_round=routes_by_round),
        )


def _routes_by_round(
    traffic: TeamTraffic, members_by_channel: dict[str, tuple[str, ...]]
) -> dict[int, set[Route]]:
    """The routes the team's charged messages took, by round."""
    routes_by_round: dict[int, set[Route]] = {}
    for message in traffic.messages:
        if message.channel_id == traffic.primary.channel_id:
            readers: tuple[str, ...] | None = traffic.member_agent_ids
        else:
            readers = members_by_channel.get(message.channel_id)
        if readers is None:
            continue
        routes = routes_by_round.setdefault(message.round_number, set())
        for reader in readers:
            if reader != message.sender_agent_id:
                routes.add((message.sender_agent_id, reader))
    return routes_by_round


def _teammates_reached(
    traffic: TeamTraffic, routes_by_round: dict[int, set[Route]]
) -> list[AgentObservation]:
    """Each member's mean number of teammates reached per round, silent members included."""
    rounds = len(routes_by_round)
    observations: list[AgentObservation] = []
    for agent_id in traffic.member_agent_ids:
        routes = sum(
            1
            for round_routes in routes_by_round.values()
            for sender, _ in round_routes
            if sender == agent_id
        )
        observations.append(
            AgentObservation(
                agent_id=agent_id,
                value=routes / rounds,
                note=f"{routes} routes over {rounds} rounds",
            )
        )
    return observations
