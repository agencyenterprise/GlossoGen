"""Assemble agent / channel / team-state configurations from veyru knobs.

The veyru scenario runs in two layouts: single-team (2 agents + optional
intern on one comm link) or two-team (4 agents over two isolated comm
links, with an optional mid-simulation observer swap). Either layout may
include the postmortem discussion channel. The factory functions here
turn a validated ``VeyruKnobs`` instance into the ``AgentConfig`` /
``Channel`` / initial ``TeamState`` collections the runtime expects.
"""

from typing import NamedTuple

from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.scenarios.veyru.ids import (
    FIELD_OBSERVER_A_ROLE,
    FIELD_OBSERVER_B_ROLE,
    FIELD_OBSERVER_ID,
    FIELD_OBSERVER_ROLE,
    FIELD_OBSERVER_SYSTEM_TEMPLATE,
    INTERN_ID,
    INTERN_ROLE,
    INTERN_SYSTEM_TEMPLATE,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    OBSERVER_A_ID,
    OBSERVER_B_ID,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    STABILIZATION_ENGINEER_A_ID,
    STABILIZATION_ENGINEER_A_ROLE,
    STABILIZATION_ENGINEER_B_ID,
    STABILIZATION_ENGINEER_B_ROLE,
    STABILIZATION_ENGINEER_ID,
    STABILIZATION_ENGINEER_ROLE,
    STABILIZATION_ENGINEER_SYSTEM_TEMPLATE,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    TOOLS_INTERN,
    TOOLS_OBSERVER,
    TOOLS_STABILIZATION_ENGINEER,
    TeamId,
)
from schmidt.scenarios.veyru.knobs import VeyruKnobs
from schmidt.scenarios.veyru.veyru_cases import FAILURE_MOTIFS
from schmidt.scenarios.veyru.world_state import TeamState
from schmidt.template_renderer import TemplateRenderer


class AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    channel_ids: list[str]
    tool_names: list[str]
    system_template: str


def build_agent_display_names(two_teams: bool, intern_enabled: bool) -> dict[str, str]:
    """Return agent display names appropriate for the active mode."""
    if two_teams:
        return {
            OBSERVER_A_ID: FIELD_OBSERVER_A_ROLE,
            STABILIZATION_ENGINEER_A_ID: STABILIZATION_ENGINEER_A_ROLE,
            OBSERVER_B_ID: FIELD_OBSERVER_B_ROLE,
            STABILIZATION_ENGINEER_B_ID: STABILIZATION_ENGINEER_B_ROLE,
            "world": "Veyru Monitor",
        }
    names: dict[str, str] = {
        FIELD_OBSERVER_ID: FIELD_OBSERVER_ROLE,
        STABILIZATION_ENGINEER_ID: STABILIZATION_ENGINEER_ROLE,
        "world": "Veyru Monitor",
    }
    if intern_enabled:
        names[INTERN_ID] = INTERN_ROLE
    return names


def build_channel_display_names(two_teams: bool, intern_enabled: bool) -> dict[str, dict[str, str]]:
    """Return channel display names keyed by channel_id then agent_id."""
    if two_teams:
        return {
            LINK_A_CHANNEL_ID: {
                OBSERVER_A_ID: "comm link",
                STABILIZATION_ENGINEER_A_ID: "comm link",
                OBSERVER_B_ID: "comm link",
                STABILIZATION_ENGINEER_B_ID: "comm link",
            },
            LINK_B_CHANNEL_ID: {
                OBSERVER_A_ID: "comm link",
                STABILIZATION_ENGINEER_A_ID: "comm link",
                OBSERVER_B_ID: "comm link",
                STABILIZATION_ENGINEER_B_ID: "comm link",
            },
            POSTMORTEM_A_CHANNEL_ID: {
                OBSERVER_A_ID: "team discussion",
                STABILIZATION_ENGINEER_A_ID: "team discussion",
                OBSERVER_B_ID: "team discussion",
                STABILIZATION_ENGINEER_B_ID: "team discussion",
            },
            POSTMORTEM_B_CHANNEL_ID: {
                OBSERVER_A_ID: "team discussion",
                STABILIZATION_ENGINEER_A_ID: "team discussion",
                OBSERVER_B_ID: "team discussion",
                STABILIZATION_ENGINEER_B_ID: "team discussion",
            },
        }
    link_members = {
        FIELD_OBSERVER_ID: "comm link",
        STABILIZATION_ENGINEER_ID: "comm link",
    }
    postmortem_members = {
        FIELD_OBSERVER_ID: "team discussion",
        STABILIZATION_ENGINEER_ID: "team discussion",
    }
    if intern_enabled:
        link_members[INTERN_ID] = "comm link"
        postmortem_members[INTERN_ID] = "team discussion"
    return {
        LINK_CHANNEL_ID: link_members,
        POSTMORTEM_CHANNEL_ID: postmortem_members,
    }


def build_teams(knobs: VeyruKnobs) -> dict[TeamId, TeamState]:
    """Construct the world's initial team state dictionary."""
    if not knobs.two_teams:
        if knobs.postmortem_enabled:
            postmortem_id: str | None = POSTMORTEM_CHANNEL_ID
        else:
            postmortem_id = None
        return {
            TEAM_SOLO_ID: TeamState(
                team_id=TEAM_SOLO_ID,
                current_observer_id=FIELD_OBSERVER_ID,
                stabilization_engineer_id=STABILIZATION_ENGINEER_ID,
                link_channel_id=LINK_CHANNEL_ID,
                postmortem_channel_id=postmortem_id,
            ),
        }
    if knobs.postmortem_enabled:
        postmortem_a: str | None = POSTMORTEM_A_CHANNEL_ID
        postmortem_b: str | None = POSTMORTEM_B_CHANNEL_ID
    else:
        postmortem_a = None
        postmortem_b = None
    return {
        TEAM_A_ID: TeamState(
            team_id=TEAM_A_ID,
            current_observer_id=OBSERVER_A_ID,
            stabilization_engineer_id=STABILIZATION_ENGINEER_A_ID,
            link_channel_id=LINK_A_CHANNEL_ID,
            postmortem_channel_id=postmortem_a,
        ),
        TEAM_B_ID: TeamState(
            team_id=TEAM_B_ID,
            current_observer_id=OBSERVER_B_ID,
            stabilization_engineer_id=STABILIZATION_ENGINEER_B_ID,
            link_channel_id=LINK_B_CHANNEL_ID,
            postmortem_channel_id=postmortem_b,
        ),
    }


def _agent_defs_single_team(knobs: VeyruKnobs, postmortem_active: bool) -> list[AgentDef]:
    """Return agent definitions for single-team mode."""
    link_channels: list[str] = [LINK_CHANNEL_ID]
    if postmortem_active:
        link_channels.append(POSTMORTEM_CHANNEL_ID)
    defs = [
        AgentDef(
            agent_id=FIELD_OBSERVER_ID,
            role_name=FIELD_OBSERVER_ROLE,
            channel_ids=list(link_channels),
            tool_names=list(TOOLS_OBSERVER),
            system_template=FIELD_OBSERVER_SYSTEM_TEMPLATE,
        ),
        AgentDef(
            agent_id=STABILIZATION_ENGINEER_ID,
            role_name=STABILIZATION_ENGINEER_ROLE,
            channel_ids=list(link_channels),
            tool_names=list(TOOLS_STABILIZATION_ENGINEER),
            system_template=STABILIZATION_ENGINEER_SYSTEM_TEMPLATE,
        ),
    ]
    if knobs.intern_enabled:
        intern_channels: list[str] = [LINK_CHANNEL_ID]
        if knobs.postmortem_enabled and knobs.postmortem_after_swap:
            intern_channels.append(POSTMORTEM_CHANNEL_ID)
        defs.append(
            AgentDef(
                agent_id=INTERN_ID,
                role_name=INTERN_ROLE,
                channel_ids=intern_channels,
                tool_names=list(TOOLS_INTERN),
                system_template=INTERN_SYSTEM_TEMPLATE,
            )
        )
    return defs


def _agent_defs_two_teams(postmortem_active: bool) -> list[AgentDef]:
    """Return agent definitions for two-team mode."""
    team_a_channels: list[str] = [LINK_A_CHANNEL_ID]
    team_b_channels: list[str] = [LINK_B_CHANNEL_ID]
    if postmortem_active:
        team_a_channels.append(POSTMORTEM_A_CHANNEL_ID)
        team_b_channels.append(POSTMORTEM_B_CHANNEL_ID)
    return [
        AgentDef(
            agent_id=OBSERVER_A_ID,
            role_name=FIELD_OBSERVER_A_ROLE,
            channel_ids=list(team_a_channels),
            tool_names=list(TOOLS_OBSERVER),
            system_template=FIELD_OBSERVER_SYSTEM_TEMPLATE,
        ),
        AgentDef(
            agent_id=STABILIZATION_ENGINEER_A_ID,
            role_name=STABILIZATION_ENGINEER_A_ROLE,
            channel_ids=list(team_a_channels),
            tool_names=list(TOOLS_STABILIZATION_ENGINEER),
            system_template=STABILIZATION_ENGINEER_SYSTEM_TEMPLATE,
        ),
        AgentDef(
            agent_id=OBSERVER_B_ID,
            role_name=FIELD_OBSERVER_B_ROLE,
            channel_ids=list(team_b_channels),
            tool_names=list(TOOLS_OBSERVER),
            system_template=FIELD_OBSERVER_SYSTEM_TEMPLATE,
        ),
        AgentDef(
            agent_id=STABILIZATION_ENGINEER_B_ID,
            role_name=STABILIZATION_ENGINEER_B_ROLE,
            channel_ids=list(team_b_channels),
            tool_names=list(TOOLS_STABILIZATION_ENGINEER),
            system_template=STABILIZATION_ENGINEER_SYSTEM_TEMPLATE,
        ),
    ]


def build_agents(
    knobs: VeyruKnobs,
    postmortem_active: bool,
    channel_display_names: dict[str, dict[str, str]],
    renderer: TemplateRenderer,
    default_model: str,
    default_provider: str,
) -> list[AgentConfig]:
    """Return ``AgentConfig`` list with rendered system prompts."""
    if knobs.two_teams:
        agent_defs = _agent_defs_two_teams(postmortem_active=postmortem_active)
    else:
        agent_defs = _agent_defs_single_team(knobs=knobs, postmortem_active=postmortem_active)
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
                            agent_id=d.agent_id,
                            channel_ids=d.channel_ids,
                            channel_display_names=channel_display_names,
                        ),
                        "postmortem_enabled": postmortem_active,
                        "intern_join_round": knobs.intern_join_round,
                        "intern_takeover_round": knobs.intern_takeover_round,
                        "failure_motifs": FAILURE_MOTIFS,
                        "channel_noise_level": knobs.channel_noise_level,
                        "noise_replacement_mode": knobs.noise_replacement_mode.value,
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


def build_channels(knobs: VeyruKnobs, postmortem_active: bool) -> list[Channel]:
    """Return communication channels appropriate for the active mode."""
    if not knobs.two_teams:
        channels: list[Channel] = [
            Channel(
                channel_id=LINK_CHANNEL_ID,
                name="link",
                member_agent_ids=[FIELD_OBSERVER_ID, STABILIZATION_ENGINEER_ID],
            ),
        ]
        if postmortem_active:
            channels.append(
                Channel(
                    channel_id=POSTMORTEM_CHANNEL_ID,
                    name="postmortem",
                    member_agent_ids=[FIELD_OBSERVER_ID, STABILIZATION_ENGINEER_ID],
                )
            )
        return channels
    two_team_channels: list[Channel] = [
        Channel(
            channel_id=LINK_A_CHANNEL_ID,
            name="link_a",
            member_agent_ids=[OBSERVER_A_ID, STABILIZATION_ENGINEER_A_ID],
        ),
        Channel(
            channel_id=LINK_B_CHANNEL_ID,
            name="link_b",
            member_agent_ids=[OBSERVER_B_ID, STABILIZATION_ENGINEER_B_ID],
        ),
    ]
    if postmortem_active:
        two_team_channels.append(
            Channel(
                channel_id=POSTMORTEM_A_CHANNEL_ID,
                name="postmortem_a",
                member_agent_ids=[OBSERVER_A_ID, STABILIZATION_ENGINEER_A_ID],
            )
        )
        two_team_channels.append(
            Channel(
                channel_id=POSTMORTEM_B_CHANNEL_ID,
                name="postmortem_b",
                member_agent_ids=[OBSERVER_B_ID, STABILIZATION_ENGINEER_B_ID],
            )
        )
    return two_team_channels


def _channel_template_data(
    agent_id: str,
    channel_ids: list[str],
    channel_display_names: dict[str, dict[str, str]],
) -> list[ChannelTemplateEntry]:
    """Build channel entries for Jinja2 system prompt templates."""
    entries: list[ChannelTemplateEntry] = []
    for cid in channel_ids:
        channel_map = channel_display_names.get(cid, {})
        display_name = channel_map.get(agent_id, cid)
        entries.append(ChannelTemplateEntry(display_name=display_name, channel_id=cid))
    return entries
