"""The channels pairs of teammates share in a ``chosen_partner`` discussion phase.

A run in that mode declares one channel for each pair of seats on a team, named
after the team's discussion channel and both seats, from 1: ``postmortem_a_1_2``.
Only the two viewers belong to it, and each is told it as its discussion with
the other.
"""

from collections.abc import Mapping
from itertools import combinations
from typing import NamedTuple

from glossogen.engine.team_declaration import TeamSpec
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.scenarios.spot_the_intersection.ids import TEAM_A_ID, TEAM_B_ID, TEAM_SOLO_ID
from glossogen.scenarios.spot_the_intersection.seats import postmortem_channel_id_for


class PartnerChannel(NamedTuple):
    """One pair channel and its two members, lower seat first."""

    channel_id: str
    first: str
    second: str

    def has_member(self, agent_id: str) -> bool:
        """Whether ``agent_id`` is one of the pair."""
        return agent_id in (self.first, self.second)

    def other(self, agent_id: str) -> str:
        """The member of the pair that is not ``agent_id``, a member."""
        if agent_id == self.first:
            return self.second
        return self.first


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


def partner_channels_of_teams(teams: tuple[TeamSpec, ...]) -> tuple[PartnerChannel, ...]:
    """Every pair channel of ``teams``, team by team in seat order."""
    return tuple(
        PartnerChannel(
            channel_id=partner_channel_id_for(
                team_id=team.team_id, first_index=first, second_index=second
            ),
            first=team.roles[first].agent_id,
            second=team.roles[second].agent_id,
        )
        for team in teams
        for first, second in combinations(range(len(team.roles)), 2)
    )


def partner_channels_of(
    pairs: tuple[PartnerChannel, ...], agent_id: str
) -> tuple[PartnerChannel, ...]:
    """The pair channels of ``pairs`` that ``agent_id`` belongs to."""
    return tuple(pair for pair in pairs if pair.has_member(agent_id=agent_id))


def declared_partner_channels(
    pairs: tuple[PartnerChannel, ...], role_names: Mapping[str, str]
) -> list[Channel]:
    """One declared channel for each of ``pairs``, named after both viewers."""
    return [
        Channel(
            channel_id=pair.channel_id,
            name=f"discussion between {role_names[pair.first]} and {role_names[pair.second]}",
            member_agent_ids=[pair.first, pair.second],
        )
        for pair in pairs
    ]


def partner_channel_entries(
    pairs: tuple[PartnerChannel, ...], role_names: Mapping[str, str], agent_id: str
) -> list[ChannelTemplateEntry]:
    """The pair channels ``agent_id`` belongs to, each named after the other member."""
    return [
        ChannelTemplateEntry(
            display_name=f"discussion with {role_names[pair.other(agent_id=agent_id)]}",
            channel_id=pair.channel_id,
        )
        for pair in partner_channels_of(pairs=pairs, agent_id=agent_id)
    ]
