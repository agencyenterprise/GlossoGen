"""Assemble agent and channel configurations from drive_module_repair knobs.

The scenario runs three agents — field technician, diagnostics engineer, and
spec engineer — on one shared bay channel, plus an optional postmortem
discussion channel. These factory functions turn a validated
``DriveModuleRepairKnobs`` instance into the ``AgentConfig`` and ``Channel``
lists the runtime expects, plus the display-name maps used by the UI.
"""

from typing import NamedTuple

from schmidt.models.agent_config import AgentConfig
from schmidt.models.channel import Channel, ChannelTemplateEntry
from schmidt.scenarios.drive_module_repair.drive_module_cases import component_access_order
from schmidt.scenarios.drive_module_repair.ids import (
    BAY_CHANNEL_ID,
    DIAGNOSTICS_ENGINEER_ID,
    DIAGNOSTICS_ENGINEER_ROLE,
    DIAGNOSTICS_ENGINEER_SYSTEM_TEMPLATE,
    FIELD_TECHNICIAN_ID,
    FIELD_TECHNICIAN_ROLE,
    FIELD_TECHNICIAN_SYSTEM_TEMPLATE,
    POSTMORTEM_CHANNEL_ID,
    SPEC_ENGINEER_ID,
    SPEC_ENGINEER_ROLE,
    SPEC_ENGINEER_SYSTEM_TEMPLATE,
    TOOLS_DIAGNOSTICS_ENGINEER,
    TOOLS_FIELD_TECHNICIAN,
    TOOLS_SPEC_ENGINEER,
)
from schmidt.scenarios.drive_module_repair.knobs import DriveModuleRepairKnobs
from schmidt.template_renderer import TemplateRenderer

BAY_CHANNEL_DISPLAY_NAME = "bay"
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
        "world": "Bay Monitor",
        FIELD_TECHNICIAN_ID: FIELD_TECHNICIAN_ROLE,
        DIAGNOSTICS_ENGINEER_ID: DIAGNOSTICS_ENGINEER_ROLE,
        SPEC_ENGINEER_ID: SPEC_ENGINEER_ROLE,
    }


def build_channel_display_names() -> dict[str, str]:
    """Return the ``channel_id`` -> display-name map."""
    return {
        BAY_CHANNEL_ID: BAY_CHANNEL_DISPLAY_NAME,
        POSTMORTEM_CHANNEL_ID: POSTMORTEM_CHANNEL_DISPLAY_NAME,
    }


def _agent_defs() -> list[_AgentDef]:
    """Return the three role definitions."""
    return [
        _AgentDef(
            agent_id=FIELD_TECHNICIAN_ID,
            role_name=FIELD_TECHNICIAN_ROLE,
            tool_names=list(TOOLS_FIELD_TECHNICIAN),
            system_template=FIELD_TECHNICIAN_SYSTEM_TEMPLATE,
        ),
        _AgentDef(
            agent_id=DIAGNOSTICS_ENGINEER_ID,
            role_name=DIAGNOSTICS_ENGINEER_ROLE,
            tool_names=list(TOOLS_DIAGNOSTICS_ENGINEER),
            system_template=DIAGNOSTICS_ENGINEER_SYSTEM_TEMPLATE,
        ),
        _AgentDef(
            agent_id=SPEC_ENGINEER_ID,
            role_name=SPEC_ENGINEER_ROLE,
            tool_names=list(TOOLS_SPEC_ENGINEER),
            system_template=SPEC_ENGINEER_SYSTEM_TEMPLATE,
        ),
    ]


def _channel_ids(postmortem_initially_active: bool) -> list[str]:
    """Return the channel IDs every agent belongs to."""
    channel_ids = [BAY_CHANNEL_ID]
    if postmortem_initially_active:
        channel_ids.append(POSTMORTEM_CHANNEL_ID)
    return channel_ids


def build_agents(
    knobs: DriveModuleRepairKnobs,
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
    access_order = [component.component_id for component in component_access_order()]
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
                        "component_access_order": access_order,
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
    """Return the bay channel plus the optional postmortem channel."""
    members = [FIELD_TECHNICIAN_ID, DIAGNOSTICS_ENGINEER_ID, SPEC_ENGINEER_ID]
    channels: list[Channel] = [
        Channel(
            channel_id=BAY_CHANNEL_ID,
            name=channel_display_names[BAY_CHANNEL_ID],
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
