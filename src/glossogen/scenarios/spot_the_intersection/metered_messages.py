"""The messages a recorded log shows a team was charged for.

A member's message on its team's link or on a direct channel costs its team,
and stops costing once every member has submitted for the round. The live world
applies that rule as messages arrive; this module applies it to an event log,
for a resume and for the metrics that split a team's count by member.
"""

from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

from glossogen.models.event import MessageSent
from glossogen.scenarios.spot_the_intersection.events import IntersectionSubmissionRecorded
from glossogen.scenarios.spot_the_intersection.world_state import TeamState, metered_team_id


class MeteredMessage(NamedTuple):
    """One message a team was charged for, and how many characters it cost."""

    round_number: int
    team_id: str
    sender_agent_id: str
    channel_id: str
    characters: int


def read_metered_messages(
    teams: Mapping[str, TeamState], events: Sequence[Any]
) -> list[MeteredMessage]:
    """Every message in ``events`` that cost its sender's team, in log order.

    A team is charged until the submission that completes it for the round, as
    in the live world.
    """
    locked: set[tuple[int, str]] = set()
    metered: list[MeteredMessage] = []
    for event in events:
        if isinstance(event, IntersectionSubmissionRecorded):
            if event.members_submitted >= event.members_required:
                locked.add((event.round_number, event.team_id))
            continue
        if not isinstance(event, MessageSent):
            continue
        team_id = metered_team_id(
            teams=teams,
            sender_agent_id=event.message.sender_agent_id,
            channel_id=event.message.channel_id,
        )
        if team_id is None or (event.round_number, team_id) in locked:
            continue
        metered.append(
            MeteredMessage(
                round_number=event.round_number,
                team_id=team_id,
                sender_agent_id=event.message.sender_agent_id,
                channel_id=event.message.channel_id,
                characters=len(event.message.text),
            )
        )
    return metered
