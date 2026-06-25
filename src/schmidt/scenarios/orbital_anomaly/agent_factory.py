"""Assemble agent and channel configurations for the orbital_anomaly scenario.

Builds the three single-team agents (astronaut, telemetry officer, systems
engineer) on one comm-loop channel plus an optional debrief channel, with
each agent's system prompt rendered from its template.
"""

from typing import NamedTuple

from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.scenarios.orbital_anomaly.ids import (
    ASTRONAUT_ID,
    ASTRONAUT_ROLE,
    ASTRONAUT_SYSTEM_TEMPLATE,
    LINK_CHANNEL_DISPLAY_NAME,
    LINK_CHANNEL_ID,
    POSTMORTEM_CHANNEL_DISPLAY_NAME,
    POSTMORTEM_CHANNEL_ID,
    SYSTEMS_ENGINEER_ID,
    SYSTEMS_ENGINEER_ROLE,
    SYSTEMS_ENGINEER_SYSTEM_TEMPLATE,
    TELEMETRY_OFFICER_ID,
    TELEMETRY_OFFICER_ROLE,
    TELEMETRY_OFFICER_SYSTEM_TEMPLATE,
    TOOLS_ASTRONAUT,
    TOOLS_SYSTEMS_ENGINEER,
    TOOLS_TELEMETRY_OFFICER,
)
from schmidt.scenarios.orbital_anomaly.knobs import OrbitalAnomalyKnobs
from schmidt.scenarios.orbital_anomaly.orbital_anomaly_cases import FAULT_SIGNATURES
from schmidt.template_renderer import TemplateRenderer


class _AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    tool_names: list[str]
    system_template: str


_AGENT_DEFS: list[_AgentDef] = [
    _AgentDef(
        agent_id=ASTRONAUT_ID,
        role_name=ASTRONAUT_ROLE,
        tool_names=list(TOOLS_ASTRONAUT),
        system_template=ASTRONAUT_SYSTEM_TEMPLATE,
    ),
    _AgentDef(
        agent_id=TELEMETRY_OFFICER_ID,
        role_name=TELEMETRY_OFFICER_ROLE,
        tool_names=list(TOOLS_TELEMETRY_OFFICER),
        system_template=TELEMETRY_OFFICER_SYSTEM_TEMPLATE,
    ),
    _AgentDef(
        agent_id=SYSTEMS_ENGINEER_ID,
        role_name=SYSTEMS_ENGINEER_ROLE,
        tool_names=list(TOOLS_SYSTEMS_ENGINEER),
        system_template=SYSTEMS_ENGINEER_SYSTEM_TEMPLATE,
    ),
]


def build_agent_display_names() -> dict[str, str]:
    """Return the ``agent_id`` → display-name map."""
    return {
        "world": "Mission Control",
        ASTRONAUT_ID: ASTRONAUT_ROLE,
        TELEMETRY_OFFICER_ID: TELEMETRY_OFFICER_ROLE,
        SYSTEMS_ENGINEER_ID: SYSTEMS_ENGINEER_ROLE,
    }


def build_channel_display_names() -> dict[str, str]:
    """Return the ``channel_id`` → display-name map."""
    return {
        LINK_CHANNEL_ID: LINK_CHANNEL_DISPLAY_NAME,
        POSTMORTEM_CHANNEL_ID: POSTMORTEM_CHANNEL_DISPLAY_NAME,
    }


def _channel_ids(postmortem_active: bool) -> list[str]:
    """Return the channel IDs every agent belongs to for the active mode."""
    channel_ids = [LINK_CHANNEL_ID]
    if postmortem_active:
        channel_ids.append(POSTMORTEM_CHANNEL_ID)
    return channel_ids


def _channel_template_data(
    channel_ids: list[str], channel_display_names: dict[str, str]
) -> list[ChannelTemplateEntry]:
    """Build channel entries for Jinja2 system prompt templates."""
    return [
        ChannelTemplateEntry(display_name=channel_display_names[cid], channel_id=cid)
        for cid in channel_ids
    ]


def build_agents(
    knobs: OrbitalAnomalyKnobs,
    postmortem_active: bool,
    channel_display_names: dict[str, str],
    renderer: TemplateRenderer,
    default_model: str,
    default_provider: str,
) -> list[AgentConfig]:
    """Return ``AgentConfig`` list with rendered system prompts."""
    channel_ids = _channel_ids(postmortem_active=postmortem_active)
    channel_entries = _channel_template_data(
        channel_ids=channel_ids,
        channel_display_names=channel_display_names,
    )
    agents: list[AgentConfig] = []
    for agent_def in _AGENT_DEFS:
        agents.append(
            AgentConfig(
                agent_id=agent_def.agent_id,
                role_name=agent_def.role_name,
                system_prompt=renderer.render(
                    template_name=agent_def.system_template,
                    template_variables={
                        "channels": channel_entries,
                        "postmortem_enabled": postmortem_active,
                        "channel_noise_level": knobs.channel_noise_level,
                        "noise_replacement_mode": knobs.noise_replacement_mode.value,
                        "fault_signatures": FAULT_SIGNATURES,
                    },
                ),
                channel_ids=list(channel_ids),
                tool_names=list(agent_def.tool_names),
                model=default_model,
                provider=default_provider,
                max_tokens=knobs.agent_max_tokens,
            )
        )
    return agents


def build_channels(
    postmortem_active: bool,
    channel_display_names: dict[str, str],
) -> list[Channel]:
    """Return the comm-loop channel plus the optional debrief channel."""
    members = [ASTRONAUT_ID, TELEMETRY_OFFICER_ID, SYSTEMS_ENGINEER_ID]
    channels = [
        Channel(
            channel_id=LINK_CHANNEL_ID,
            name=channel_display_names[LINK_CHANNEL_ID],
            member_agent_ids=list(members),
        ),
    ]
    if postmortem_active:
        channels.append(
            Channel(
                channel_id=POSTMORTEM_CHANNEL_ID,
                name=channel_display_names[POSTMORTEM_CHANNEL_ID],
                member_agent_ids=list(members),
            )
        )
    return channels
