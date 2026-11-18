"""The channels pairs of teammates share in a ``chosen_partner`` discussion phase.

A run in that mode declares one channel for each pair of seats on a team, named
after the team's discussion channel and both seats, from 1: ``postmortem_a_1_2``.
Only the two viewers belong to it, and each is told it as its discussion with
the other.
"""

from collections.abc import Mapping
from itertools import combinations

from glossogen.engine.team_declaration import TeamSpec
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.scenarios.spot_the_intersection.ids import TEAM_A_ID, TEAM_B_ID, TEAM_SOLO_ID
from glossogen.scenarios.spot_the_intersection.seats import postmortem_channel_id_for


def partner_channel_id_for(team_id: str, first_index: int, second_index: int) -> str:
    """The channel seats ``first_index`` and ``second_index`` (from 0) of ``team_id`` share."""
    low, high = sorted((first_index, second_index))
    return f"{postmortem_channel_id_for(team_id=team_id)}_{low + 1}_{high + 1}"


def every_partner_channel_id(max_team_size: int) -> frozenset[str]:
    """Every pair channel id any team of up to ``max_team_size`` seats can declare."""
    return frozenset(
        partner_channel_id_for(team_id=team_id, first_index=first, second_index=second)
        for team_id in (TEAM_SOLO_ID, TEAM_A_ID, TEAM_B_ID)
        for first, second in combinations(range(max_team_size), 2)
    )


def partner_channel_members(teams: tuple[TeamSpec, ...]) -> dict[str, tuple[str, str]]:
    """Map each pair channel of ``teams`` to its two members, lower seat first."""
    members: dict[str, tuple[str, str]] = {}
    for team in teams:
        for first, second in combinations(range(len(team.roles)), 2):
            channel_id = partner_channel_id_for(
                team_id=team.team_id, first_index=first, second_index=second
            )
            members[channel_id] = (team.roles[first].agent_id, team.roles[second].agent_id)
    return members


def partner_channels(
    members: Mapping[str, tuple[str, str]], role_names: Mapping[str, str]
) -> list[Channel]:
    """One channel for each entry of ``members``, named after both viewers."""
    return [
        Channel(
            channel_id=channel_id,
            name=f"discussion between {role_names[first]} and {role_names[second]}",
            member_agent_ids=[first, second],
        )
        for channel_id, (first, second) in members.items()
    ]


def partner_channel_entries(
    members: Mapping[str, tuple[str, str]], role_names: Mapping[str, str], agent_id: str
) -> list[ChannelTemplateEntry]:
    """The pair channels ``agent_id`` belongs to, each named after the other member."""
    entries: list[ChannelTemplateEntry] = []
    for channel_id, (first, second) in members.items():
        if agent_id not in (first, second):
            continue
        other = first
        if first == agent_id:
            other = second
        entries.append(
            ChannelTemplateEntry(
                display_name=f"discussion with {role_names[other]}", channel_id=channel_id
            )
        )
    return entries
