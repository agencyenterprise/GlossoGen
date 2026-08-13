"""Satellite contact window's structure, stated as engine declarations.

One team on a shared link: a telemetry operator who can send the command
sequence, a subsystem engineer, and a flight director. The debrief follows each
round when the knobs enable it.
"""

from glossogen.engine.team_declaration import (
    Debrief,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)
from glossogen.scenarios.satellite_contact_window.ids import (
    FLIGHT_DIRECTOR_ID,
    FLIGHT_DIRECTOR_ROLE,
    FLIGHT_DIRECTOR_SYSTEM_TEMPLATE,
    LINK_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    SUBSYSTEM_ENGINEER_ID,
    SUBSYSTEM_ENGINEER_ROLE,
    SUBSYSTEM_ENGINEER_SYSTEM_TEMPLATE,
    TELEMETRY_OPERATOR_ID,
    TELEMETRY_OPERATOR_ROLE,
    TELEMETRY_OPERATOR_SYSTEM_TEMPLATE,
    TOOLS_FLIGHT_DIRECTOR,
    TOOLS_SUBSYSTEM_ENGINEER,
    TOOLS_TELEMETRY_OPERATOR,
)
from glossogen.scenarios.satellite_contact_window.knobs import SatelliteContactWindowKnobs

TEAM_ID = "solo"
LINK_DISPLAY_NAME = "link"
DEBRIEF_DISPLAY_NAME = "team discussion"


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


def satellite_teams(knobs: SatelliteContactWindowKnobs) -> tuple[TeamSpec, ...]:
    """Return the single team this scenario runs."""
    if knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start:
        debrief = Debrief(
            channel_id=POSTMORTEM_CHANNEL_ID,
            name="postmortem",
            display_name=DEBRIEF_DISPLAY_NAME,
        )
    else:
        debrief = NoDebrief()
    return (
        TeamSpec(
            team_id=TEAM_ID,
            task=TaskChannel(
                channel_id=LINK_CHANNEL_ID, name="link", display_name=LINK_DISPLAY_NAME
            ),
            debrief=debrief,
            roles=(
                _role(
                    agent_id=TELEMETRY_OPERATOR_ID,
                    role_name=TELEMETRY_OPERATOR_ROLE,
                    system_template=TELEMETRY_OPERATOR_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_TELEMETRY_OPERATOR),
                ),
                _role(
                    agent_id=SUBSYSTEM_ENGINEER_ID,
                    role_name=SUBSYSTEM_ENGINEER_ROLE,
                    system_template=SUBSYSTEM_ENGINEER_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_SUBSYSTEM_ENGINEER),
                ),
                _role(
                    agent_id=FLIGHT_DIRECTOR_ID,
                    role_name=FLIGHT_DIRECTOR_ROLE,
                    system_template=FLIGHT_DIRECTOR_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_FLIGHT_DIRECTOR),
                ),
            ),
        ),
    )
