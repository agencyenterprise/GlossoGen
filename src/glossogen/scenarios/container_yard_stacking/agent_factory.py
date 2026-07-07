"""Assemble agent and channel configurations from yard-scenario knobs.

The yard scenario runs in three layouts: solo (3 agents on one link channel,
optional 4th intern), two-team (6 agents over two link channels), and either
with or without the postmortem discussion channel. The factory functions
here turn a validated ``ContainerYardStackingKnobs`` instance into the
``AgentConfig`` and ``Channel`` lists the runtime expects, plus the
display-name maps used in injection rendering and the UI.
"""

from typing import NamedTuple

from glossogen.models.agent_config import AgentConfig
from glossogen.models.channel import Channel, ChannelTemplateEntry
from glossogen.scenarios.container_yard_stacking.ids import (
    CRANE_OPERATOR_A_ID,
    CRANE_OPERATOR_A_ROLE,
    CRANE_OPERATOR_B_ID,
    CRANE_OPERATOR_B_ROLE,
    CRANE_OPERATOR_ID,
    CRANE_OPERATOR_ROLE,
    CRANE_OPERATOR_SYSTEM_TEMPLATE,
    INTERN_ID,
    INTERN_ROLE,
    INTERN_SYSTEM_TEMPLATE,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    LOGISTICS_PLANNER_A_ID,
    LOGISTICS_PLANNER_A_ROLE,
    LOGISTICS_PLANNER_B_ID,
    LOGISTICS_PLANNER_B_ROLE,
    LOGISTICS_PLANNER_ID,
    LOGISTICS_PLANNER_ROLE,
    LOGISTICS_PLANNER_SYSTEM_TEMPLATE,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    TOOLS_CRANE_OPERATOR,
    TOOLS_INTERN,
    TOOLS_LOGISTICS_PLANNER,
    TOOLS_YARD_OPERATOR,
    YARD_OPERATOR_A_ID,
    YARD_OPERATOR_A_ROLE,
    YARD_OPERATOR_B_ID,
    YARD_OPERATOR_B_ROLE,
    YARD_OPERATOR_ID,
    YARD_OPERATOR_ROLE,
    YARD_OPERATOR_SYSTEM_TEMPLATE,
)
from glossogen.scenarios.container_yard_stacking.knobs import ContainerYardStackingKnobs
from glossogen.scenarios.container_yard_stacking.team_routing import (
    crane_operator_id_for_team,
    link_channel_id_for_team,
    logistics_planner_id_for_team,
    postmortem_channel_id_for_team,
    yard_operator_id_for_team,
)
from glossogen.template_renderer import TemplateRenderer


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    system_template: str


def build_agent_display_names(two_teams: bool, intern_enabled: bool) -> dict[str, str]:
    """Return ``agent_id`` → display-name map for the current mode."""
    names: dict[str, str] = {"world": "Yard Monitor"}
    if two_teams:
        names[YARD_OPERATOR_A_ID] = YARD_OPERATOR_A_ROLE
        names[LOGISTICS_PLANNER_A_ID] = LOGISTICS_PLANNER_A_ROLE
        names[CRANE_OPERATOR_A_ID] = CRANE_OPERATOR_A_ROLE
        names[YARD_OPERATOR_B_ID] = YARD_OPERATOR_B_ROLE
        names[LOGISTICS_PLANNER_B_ID] = LOGISTICS_PLANNER_B_ROLE
        names[CRANE_OPERATOR_B_ID] = CRANE_OPERATOR_B_ROLE
    else:
        names[YARD_OPERATOR_ID] = YARD_OPERATOR_ROLE
        names[LOGISTICS_PLANNER_ID] = LOGISTICS_PLANNER_ROLE
        names[CRANE_OPERATOR_ID] = CRANE_OPERATOR_ROLE
        if intern_enabled:
            names[INTERN_ID] = INTERN_ROLE
    return names


def build_channel_display_names(two_teams: bool) -> dict[str, str]:
    """Return ``channel_id`` → display-name map for the current mode."""
    if two_teams:
        return {
            LINK_A_CHANNEL_ID: "link (Team A)",
            LINK_B_CHANNEL_ID: "link (Team B)",
            POSTMORTEM_A_CHANNEL_ID: "team discussion (Team A)",
            POSTMORTEM_B_CHANNEL_ID: "team discussion (Team B)",
        }
    return {
        LINK_CHANNEL_ID: "link",
        POSTMORTEM_CHANNEL_ID: "team discussion",
    }


def build_agent_defs(
    knobs: ContainerYardStackingKnobs,
    postmortem_initially_active: bool,
    agent_display_names: dict[str, str],
) -> list[AgentDef]:
    """Return the agent definition list — 3 single-team, 4 with intern, 6 two-team."""
    if knobs.two_teams:
        return [
            *_agent_defs_for_team(
                team_id=TEAM_A_ID,
                postmortem_initially_active=postmortem_initially_active,
                agent_display_names=agent_display_names,
            ),
            *_agent_defs_for_team(
                team_id=TEAM_B_ID,
                postmortem_initially_active=postmortem_initially_active,
                agent_display_names=agent_display_names,
            ),
        ]
    defs = _agent_defs_for_team(
        team_id=TEAM_SOLO_ID,
        postmortem_initially_active=postmortem_initially_active,
        agent_display_names=agent_display_names,
    )
    if knobs.intern_enabled:
        team_channels = [LINK_CHANNEL_ID]
        if postmortem_initially_active:
            team_channels.append(POSTMORTEM_CHANNEL_ID)
        defs.append(
            AgentDef(
                agent_id=INTERN_ID,
                role_name=INTERN_ROLE,
                channel_ids=team_channels,
                tool_names=list(TOOLS_INTERN),
                system_template=INTERN_SYSTEM_TEMPLATE,
            )
        )
    return defs


def _agent_defs_for_team(
    team_id: str,
    postmortem_initially_active: bool,
    agent_display_names: dict[str, str],
) -> list[AgentDef]:
    """Build the three role definitions scoped to one team."""
    link_id = link_channel_id_for_team(team_id=team_id)
    postmortem_id = postmortem_channel_id_for_team(team_id=team_id)
    team_channels: list[str] = [link_id]
    if postmortem_initially_active:
        team_channels.append(postmortem_id)
    yard_id = yard_operator_id_for_team(team_id=team_id)
    planner_id = logistics_planner_id_for_team(team_id=team_id)
    crane_id = crane_operator_id_for_team(team_id=team_id)
    return [
        AgentDef(
            agent_id=yard_id,
            role_name=agent_display_names[yard_id],
            channel_ids=list(team_channels),
            tool_names=list(TOOLS_YARD_OPERATOR),
            system_template=YARD_OPERATOR_SYSTEM_TEMPLATE,
        ),
        AgentDef(
            agent_id=planner_id,
            role_name=agent_display_names[planner_id],
            channel_ids=list(team_channels),
            tool_names=list(TOOLS_LOGISTICS_PLANNER),
            system_template=LOGISTICS_PLANNER_SYSTEM_TEMPLATE,
        ),
        AgentDef(
            agent_id=crane_id,
            role_name=agent_display_names[crane_id],
            channel_ids=list(team_channels),
            tool_names=list(TOOLS_CRANE_OPERATOR),
            system_template=CRANE_OPERATOR_SYSTEM_TEMPLATE,
        ),
    ]


def build_agents(
    knobs: ContainerYardStackingKnobs,
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
    for d in agent_defs:
        agents.append(
            AgentConfig(
                agent_id=d.agent_id,
                role_name=d.role_name,
                system_prompt=renderer.render(
                    template_name=d.system_template,
                    template_variables={
                        "channels": _channel_template_data(
                            channel_ids=d.channel_ids,
                            channel_display_names=channel_display_names,
                        ),
                        "postmortem_enabled": postmortem_initially_active,
                        "channel_noise_level": knobs.channel_noise_level,
                        "noise_replacement_mode": knobs.noise_replacement_mode.value,
                        "intern_join_round": knobs.intern_join_round,
                        "intern_takeover_round": knobs.intern_takeover_round,
                    },
                ),
                channel_ids=d.channel_ids,
                tool_names=d.tool_names,
                model=default_model,
                provider=default_provider,
                max_tokens=knobs.agent_max_tokens,
                compaction=knobs.compaction,
            )
        )
    return agents


def build_channels(
    knobs: ContainerYardStackingKnobs,
    postmortem_initially_active: bool,
    channel_display_names: dict[str, str],
) -> list[Channel]:
    """Return per-team link + (optional) postmortem channels."""
    if not knobs.two_teams:
        return _channels_for_team(
            team_id=TEAM_SOLO_ID,
            intern_enabled=knobs.intern_enabled,
            postmortem_initially_active=postmortem_initially_active,
            channel_display_names=channel_display_names,
        )
    return [
        *_channels_for_team(
            team_id=TEAM_A_ID,
            intern_enabled=knobs.intern_enabled,
            postmortem_initially_active=postmortem_initially_active,
            channel_display_names=channel_display_names,
        ),
        *_channels_for_team(
            team_id=TEAM_B_ID,
            intern_enabled=knobs.intern_enabled,
            postmortem_initially_active=postmortem_initially_active,
            channel_display_names=channel_display_names,
        ),
    ]


def _channels_for_team(
    team_id: str,
    intern_enabled: bool,
    postmortem_initially_active: bool,
    channel_display_names: dict[str, str],
) -> list[Channel]:
    """Build link and (optional) postmortem channels scoped to one team."""
    link_id = link_channel_id_for_team(team_id=team_id)
    postmortem_id = postmortem_channel_id_for_team(team_id=team_id)
    members = [
        yard_operator_id_for_team(team_id=team_id),
        logistics_planner_id_for_team(team_id=team_id),
        crane_operator_id_for_team(team_id=team_id),
    ]
    if team_id == TEAM_SOLO_ID and intern_enabled:
        members.append(INTERN_ID)
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
