"""Assemble agent and channel configurations from spot_the_difference knobs.

The scenario runs in two layouts: solo (two viewers on one link channel) and
two-team (four viewers over two link channels), each with or without the
postmortem discussion channel. Both viewers on a team are symmetric — they
differ only in which scene they hold (left = scene A, right = scene B) — so
they get the same tool set and channels, differing only in their system
template.
"""

from typing import NamedTuple

from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.scenarios.spot_the_difference.ids import (
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    TOOLS_VIEWER,
    VIEWER_LEFT_A_ID,
    VIEWER_LEFT_A_ROLE,
    VIEWER_LEFT_B_ID,
    VIEWER_LEFT_B_ROLE,
    VIEWER_LEFT_ID,
    VIEWER_LEFT_ROLE,
    VIEWER_LEFT_SYSTEM_TEMPLATE,
    VIEWER_RIGHT_A_ID,
    VIEWER_RIGHT_A_ROLE,
    VIEWER_RIGHT_B_ID,
    VIEWER_RIGHT_B_ROLE,
    VIEWER_RIGHT_ID,
    VIEWER_RIGHT_ROLE,
    VIEWER_RIGHT_SYSTEM_TEMPLATE,
)
from schmidt.scenarios.spot_the_difference.knobs import SpotTheDifferenceKnobs
from schmidt.scenarios.spot_the_difference.team_routing import (
    link_channel_id_for_team,
    postmortem_channel_id_for_team,
    viewer_left_id_for_team,
    viewer_right_id_for_team,
)
from schmidt.template_renderer import TemplateRenderer


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    system_template: str


def _team_ids_for_mode(two_teams: bool) -> list[str]:
    """Return the active team IDs for the current mode."""
    if two_teams:
        return [TEAM_A_ID, TEAM_B_ID]
    return [TEAM_SOLO_ID]


def build_agent_display_names(two_teams: bool) -> dict[str, str]:
    """Return ``agent_id`` -> display-name map for the current mode."""
    names: dict[str, str] = {"world": "Game Host"}
    if two_teams:
        names[VIEWER_LEFT_A_ID] = VIEWER_LEFT_A_ROLE
        names[VIEWER_RIGHT_A_ID] = VIEWER_RIGHT_A_ROLE
        names[VIEWER_LEFT_B_ID] = VIEWER_LEFT_B_ROLE
        names[VIEWER_RIGHT_B_ID] = VIEWER_RIGHT_B_ROLE
    else:
        names[VIEWER_LEFT_ID] = VIEWER_LEFT_ROLE
        names[VIEWER_RIGHT_ID] = VIEWER_RIGHT_ROLE
    return names


def build_channel_display_names(two_teams: bool) -> dict[str, str]:
    """Return ``channel_id`` -> display-name map for the current mode."""
    if two_teams:
        return {
            link_channel_id_for_team(team_id=TEAM_A_ID): "link (Team A)",
            link_channel_id_for_team(team_id=TEAM_B_ID): "link (Team B)",
            postmortem_channel_id_for_team(team_id=TEAM_A_ID): "team discussion (Team A)",
            postmortem_channel_id_for_team(team_id=TEAM_B_ID): "team discussion (Team B)",
        }
    return {
        link_channel_id_for_team(team_id=TEAM_SOLO_ID): "link",
        postmortem_channel_id_for_team(team_id=TEAM_SOLO_ID): "team discussion",
    }


def _agent_defs_for_team(
    team_id: str,
    postmortem_initially_active: bool,
    agent_display_names: dict[str, str],
) -> list[AgentDef]:
    """Build the two symmetric viewer definitions scoped to one team."""
    link_id = link_channel_id_for_team(team_id=team_id)
    postmortem_id = postmortem_channel_id_for_team(team_id=team_id)
    team_channels: list[str] = [link_id]
    if postmortem_initially_active:
        team_channels.append(postmortem_id)
    left_id = viewer_left_id_for_team(team_id=team_id)
    right_id = viewer_right_id_for_team(team_id=team_id)
    return [
        AgentDef(
            agent_id=left_id,
            role_name=agent_display_names[left_id],
            channel_ids=list(team_channels),
            tool_names=list(TOOLS_VIEWER),
            system_template=VIEWER_LEFT_SYSTEM_TEMPLATE,
        ),
        AgentDef(
            agent_id=right_id,
            role_name=agent_display_names[right_id],
            channel_ids=list(team_channels),
            tool_names=list(TOOLS_VIEWER),
            system_template=VIEWER_RIGHT_SYSTEM_TEMPLATE,
        ),
    ]


def build_agent_defs(
    knobs: SpotTheDifferenceKnobs,
    postmortem_initially_active: bool,
    agent_display_names: dict[str, str],
) -> list[AgentDef]:
    """Return the agent definition list — 2 single-team, 4 two-team."""
    defs: list[AgentDef] = []
    for team_id in _team_ids_for_mode(two_teams=knobs.two_teams):
        defs.extend(
            _agent_defs_for_team(
                team_id=team_id,
                postmortem_initially_active=postmortem_initially_active,
                agent_display_names=agent_display_names,
            )
        )
    return defs


def _channel_template_data(
    channel_ids: list[str], channel_display_names: dict[str, str]
) -> list[ChannelTemplateEntry]:
    """Build channel entries for Jinja2 system prompt templates."""
    return [
        ChannelTemplateEntry(
            display_name=channel_display_names.get(cid, cid),
            channel_id=cid,
        )
        for cid in channel_ids
    ]


def build_agents(
    knobs: SpotTheDifferenceKnobs,
    postmortem_initially_active: bool,
    agent_display_names: dict[str, str],
    channel_display_names: dict[str, str],
    renderer: TemplateRenderer,
    default_model: str,
    default_provider: str,
) -> list[AgentConfig]:
    """Return ``AgentConfig`` list with rendered system prompts."""
    agent_defs = build_agent_defs(
        knobs=knobs,
        postmortem_initially_active=postmortem_initially_active,
        agent_display_names=agent_display_names,
    )
    agents: list[AgentConfig] = []
    for definition in agent_defs:
        agents.append(
            AgentConfig(
                agent_id=definition.agent_id,
                role_name=definition.role_name,
                system_prompt=renderer.render(
                    template_name=definition.system_template,
                    template_variables={
                        "channels": _channel_template_data(
                            channel_ids=definition.channel_ids,
                            channel_display_names=channel_display_names,
                        ),
                        "postmortem_enabled": postmortem_initially_active,
                        "channel_noise_level": knobs.channel_noise_level,
                        "noise_replacement_mode": knobs.noise_replacement_mode.value,
                        "two_teams": knobs.two_teams,
                        "all_must_submit": knobs.all_must_submit,
                        "round_time_budget_seconds": knobs.round_time_budget_seconds,
                        "grid_size": knobs.grid_size,
                        "difference_kinds": knobs.difference_kinds,
                    },
                ),
                channel_ids=definition.channel_ids,
                tool_names=definition.tool_names,
                model=default_model,
                provider=default_provider,
                max_tokens=knobs.agent_max_tokens,
            )
        )
    return agents


def _channels_for_team(
    team_id: str,
    postmortem_initially_active: bool,
    channel_display_names: dict[str, str],
) -> list[Channel]:
    """Build link and (optional) postmortem channels scoped to one team."""
    link_id = link_channel_id_for_team(team_id=team_id)
    postmortem_id = postmortem_channel_id_for_team(team_id=team_id)
    members = [
        viewer_left_id_for_team(team_id=team_id),
        viewer_right_id_for_team(team_id=team_id),
    ]
    channels: list[Channel] = [
        Channel(
            channel_id=link_id,
            name=channel_display_names[link_id],
            member_agent_ids=list(members),
        ),
    ]
    if postmortem_initially_active:
        channels.append(
            Channel(
                channel_id=postmortem_id,
                name=channel_display_names[postmortem_id],
                member_agent_ids=list(members),
            )
        )
    return channels


def build_channels(
    knobs: SpotTheDifferenceKnobs,
    postmortem_initially_active: bool,
    channel_display_names: dict[str, str],
) -> list[Channel]:
    """Return per-team link + (optional) postmortem channels."""
    channels: list[Channel] = []
    for team_id in _team_ids_for_mode(two_teams=knobs.two_teams):
        channels.extend(
            _channels_for_team(
                team_id=team_id,
                postmortem_initially_active=postmortem_initially_active,
                channel_display_names=channel_display_names,
            )
        )
    return channels
