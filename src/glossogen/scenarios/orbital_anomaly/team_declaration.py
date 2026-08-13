"""Orbital anomaly's structure, stated as engine declarations.

One team on the comm loop: an astronaut who can actuate the panel, a telemetry
officer reading the downlink, and a systems engineer holding the procedures.
All three hold the debrief when the knobs enable it.
"""

from glossogen.engine.team_declaration import (
    Debrief,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)
from glossogen.scenarios.orbital_anomaly.ids import (
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
from glossogen.scenarios.orbital_anomaly.knobs import OrbitalAnomalyKnobs

TEAM_ID = "solo"


def _role(
    agent_id: str, role_name: str, system_template: str, tool_names: tuple[str, ...]
) -> RoleSpec:
    """Build one of the three roles; all are present from round one."""
    return RoleSpec(
        agent_id=agent_id,
        role_name=role_name,
        system_template=system_template,
        tool_names=tool_names,
        joins_debrief=True,
        starts_as_member=True,
    )


def orbital_teams(knobs: OrbitalAnomalyKnobs) -> tuple[TeamSpec, ...]:
    """Return the single team this scenario runs."""
    if knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start:
        debrief = Debrief(
            channel_id=POSTMORTEM_CHANNEL_ID,
            # This scenario names the channel after how agents are told to call
            # it, so the name and the display name are the same string.
            name=POSTMORTEM_CHANNEL_DISPLAY_NAME,
            display_name=POSTMORTEM_CHANNEL_DISPLAY_NAME,
        )
    else:
        debrief = NoDebrief()
    return (
        TeamSpec(
            team_id=TEAM_ID,
            task=TaskChannel(
                channel_id=LINK_CHANNEL_ID,
                name=LINK_CHANNEL_DISPLAY_NAME,
                display_name=LINK_CHANNEL_DISPLAY_NAME,
            ),
            debrief=debrief,
            roles=(
                _role(
                    agent_id=ASTRONAUT_ID,
                    role_name=ASTRONAUT_ROLE,
                    system_template=ASTRONAUT_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_ASTRONAUT),
                ),
                _role(
                    agent_id=TELEMETRY_OFFICER_ID,
                    role_name=TELEMETRY_OFFICER_ROLE,
                    system_template=TELEMETRY_OFFICER_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_TELEMETRY_OFFICER),
                ),
                _role(
                    agent_id=SYSTEMS_ENGINEER_ID,
                    role_name=SYSTEMS_ENGINEER_ROLE,
                    system_template=SYSTEMS_ENGINEER_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_SYSTEMS_ENGINEER),
                ),
            ),
        ),
    )
