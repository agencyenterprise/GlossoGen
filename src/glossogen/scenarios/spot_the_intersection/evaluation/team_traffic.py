"""Each team's charged messages, the input of the metrics that split a team's count by member."""

from typing import NamedTuple

from glossogen.models.event import SimulationEvent
from glossogen.scenario_contract.scenario_base import PrimaryChannel, ScenarioBase
from glossogen.scenarios.spot_the_intersection.ids import TEAM_SOLO_ID
from glossogen.scenarios.spot_the_intersection.metered_messages import MeteredMessage
from glossogen.scenarios.spot_the_intersection.world import SpotTheIntersectionWorld


class TeamTraffic(NamedTuple):
    """One team's primary channel, its members, and the messages it was charged for."""

    primary: PrimaryChannel
    member_agent_ids: tuple[str, ...]
    messages: list[MeteredMessage]


def team_traffic(scenario: ScenarioBase, events: list[SimulationEvent]) -> list[TeamTraffic]:
    """One entry per primary channel, with the messages its team was charged for in ``events``."""
    world = scenario.get_world()
    if not isinstance(world, SpotTheIntersectionWorld):
        raise TypeError(f"expected a spot_the_intersection world, got {type(world).__name__}")
    messages = world.metered_messages(events=events)
    traffic: list[TeamTraffic] = []
    for primary in scenario.get_primary_channels():
        team_id = primary.team_id
        if team_id is None:
            team_id = TEAM_SOLO_ID
        traffic.append(
            TeamTraffic(
                primary=primary,
                member_agent_ids=tuple(
                    agent_id for agent_id, seat in world.seats.items() if seat.team_id == team_id
                ),
                messages=[message for message in messages if message.team_id == team_id],
            )
        )
    return traffic
