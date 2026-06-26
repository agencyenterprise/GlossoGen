"""Assemble agent and channel configurations from spillway-scenario knobs.

The scenario runs three agents — dam operator, civil defense coordinator,
and park ranger — on one shared ops channel, plus an optional postmortem
discussion channel. These factory functions turn a validated
``SpillwayReleaseKnobs`` instance into the ``AgentConfig`` and ``Channel``
lists the runtime expects, plus the display-name maps used by the UI.
"""

from typing import NamedTuple

from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.scenarios.spillway_release.ids import (
    CIVIL_DEFENSE_ID,
    CIVIL_DEFENSE_ROLE,
    CIVIL_DEFENSE_SYSTEM_TEMPLATE,
    DAM_OPERATOR_ID,
    DAM_OPERATOR_ROLE,
    DAM_OPERATOR_SYSTEM_TEMPLATE,
    OPS_CHANNEL_ID,
    PARK_RANGER_ID,
    PARK_RANGER_ROLE,
    PARK_RANGER_SYSTEM_TEMPLATE,
    POSTMORTEM_CHANNEL_ID,
    TOOLS_CIVIL_DEFENSE,
    TOOLS_DAM_OPERATOR,
    TOOLS_PARK_RANGER,
)
from schmidt.scenarios.spillway_release.knobs import SpillwayReleaseKnobs
from schmidt.template_renderer import TemplateRenderer

OPS_CHANNEL_DISPLAY_NAME = "ops"
POSTMORTEM_CHANNEL_DISPLAY_NAME = "team discussion"


class _AgentDef(NamedTuple):
    """Lightweight definition of an agent before full AgentConfig construction."""

    agent_id: str
    role_name: str
    tool_names: list[str]
    system_template: str


def build_agent_display_names() -> dict[str, str]:
    """Return the ``agent_id`` -> display-name map."""
    return {
        "world": "Reservoir Monitor",
        DAM_OPERATOR_ID: DAM_OPERATOR_ROLE,
        CIVIL_DEFENSE_ID: CIVIL_DEFENSE_ROLE,
        PARK_RANGER_ID: PARK_RANGER_ROLE,
    }


def build_channel_display_names() -> dict[str, str]:
    """Return the ``channel_id`` -> display-name map."""
    return {
        OPS_CHANNEL_ID: OPS_CHANNEL_DISPLAY_NAME,
        POSTMORTEM_CHANNEL_ID: POSTMORTEM_CHANNEL_DISPLAY_NAME,
    }


def _agent_defs() -> list[_AgentDef]:
    """Return the three role definitions."""
    return [
        _AgentDef(
            agent_id=DAM_OPERATOR_ID,
            role_name=DAM_OPERATOR_ROLE,
            tool_names=list(TOOLS_DAM_OPERATOR),
            system_template=DAM_OPERATOR_SYSTEM_TEMPLATE,
        ),
        _AgentDef(
            agent_id=CIVIL_DEFENSE_ID,
            role_name=CIVIL_DEFENSE_ROLE,
            tool_names=list(TOOLS_CIVIL_DEFENSE),
            system_template=CIVIL_DEFENSE_SYSTEM_TEMPLATE,
        ),
        _AgentDef(
            agent_id=PARK_RANGER_ID,
            role_name=PARK_RANGER_ROLE,
            tool_names=list(TOOLS_PARK_RANGER),
            system_template=PARK_RANGER_SYSTEM_TEMPLATE,
        ),
    ]


def _channel_ids(postmortem_initially_active: bool) -> list[str]:
    """Return the channel IDs every agent belongs to."""
    channel_ids = [OPS_CHANNEL_ID]
    if postmortem_initially_active:
        channel_ids.append(POSTMORTEM_CHANNEL_ID)
    return channel_ids


def build_agents(
    knobs: SpillwayReleaseKnobs,
    postmortem_initially_active: bool,
    channel_display_names: dict[str, str],
    renderer: TemplateRenderer,
    default_model: str,
    default_provider: str,
) -> list[AgentConfig]:
    """Return the ``AgentConfig`` list with rendered system prompts."""
    channel_ids = _channel_ids(postmortem_initially_active=postmortem_initially_active)
    channels_for_template = [
        ChannelTemplateEntry(
            display_name=channel_display_names.get(cid, cid),
            channel_id=cid,
        )
        for cid in channel_ids
    ]
    agents: list[AgentConfig] = []
    for d in _agent_defs():
        agents.append(
            AgentConfig(
                agent_id=d.agent_id,
                role_name=d.role_name,
                system_prompt=renderer.render(
                    template_name=d.system_template,
                    template_variables={
                        "channels": channels_for_template,
                        "postmortem_enabled": postmortem_initially_active,
                        "channel_noise_level": knobs.channel_noise_level,
                        "noise_replacement_mode": knobs.noise_replacement_mode.value,
                        "gate_count": knobs.gate_count,
                        "release_per_gate_per_hour": knobs.release_per_gate_per_hour,
                        "max_level": knobs.max_level,
                        "min_level": knobs.min_level,
                    },
                ),
                channel_ids=list(channel_ids),
                tool_names=d.tool_names,
                model=default_model,
                provider=default_provider,
                max_tokens=knobs.agent_max_tokens,
            )
        )
    return agents


def build_channels(
    postmortem_initially_active: bool,
    channel_display_names: dict[str, str],
) -> list[Channel]:
    """Return the ops channel plus the optional postmortem channel."""
    members = [DAM_OPERATOR_ID, CIVIL_DEFENSE_ID, PARK_RANGER_ID]
    channels: list[Channel] = [
        Channel(
            channel_id=OPS_CHANNEL_ID,
            name=channel_display_names[OPS_CHANNEL_ID],
            member_agent_ids=list(members),
        ),
    ]
    if postmortem_initially_active:
        channels.append(
            Channel(
                channel_id=POSTMORTEM_CHANNEL_ID,
                name=channel_display_names[POSTMORTEM_CHANNEL_ID],
                member_agent_ids=list(members),
            )
        )
    return channels
