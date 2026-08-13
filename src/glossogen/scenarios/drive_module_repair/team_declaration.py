"""Drive module repair's structure, stated as engine declarations.

One team in the bay: a field technician at the unit who can service components,
a diagnostics engineer reading the fault trace, and a spec engineer holding the
replacement sheets. All three hold the debrief when the knobs enable it.
"""

from glossogen.engine.team_declaration import (
    Debrief,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)
from glossogen.scenarios.drive_module_repair.ids import (
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
from glossogen.scenarios.drive_module_repair.knobs import DriveModuleRepairKnobs

TEAM_ID = "solo"
BAY_DISPLAY_NAME = "bay"
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


def drive_module_teams(knobs: DriveModuleRepairKnobs) -> tuple[TeamSpec, ...]:
    """Return the single team this scenario runs."""
    if knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start:
        debrief = Debrief(
            channel_id=POSTMORTEM_CHANNEL_ID,
            # This scenario names the channel after how agents are told to call
            # it, so the name and the display name are the same string.
            name=DEBRIEF_DISPLAY_NAME,
            display_name=DEBRIEF_DISPLAY_NAME,
        )
    else:
        debrief = NoDebrief()
    return (
        TeamSpec(
            team_id=TEAM_ID,
            task=TaskChannel(
                channel_id=BAY_CHANNEL_ID,
                name=BAY_DISPLAY_NAME,
                display_name=BAY_DISPLAY_NAME,
            ),
            debrief=debrief,
            roles=(
                _role(
                    agent_id=FIELD_TECHNICIAN_ID,
                    role_name=FIELD_TECHNICIAN_ROLE,
                    system_template=FIELD_TECHNICIAN_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_FIELD_TECHNICIAN),
                ),
                _role(
                    agent_id=DIAGNOSTICS_ENGINEER_ID,
                    role_name=DIAGNOSTICS_ENGINEER_ROLE,
                    system_template=DIAGNOSTICS_ENGINEER_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_DIAGNOSTICS_ENGINEER),
                ),
                _role(
                    agent_id=SPEC_ENGINEER_ID,
                    role_name=SPEC_ENGINEER_ROLE,
                    system_template=SPEC_ENGINEER_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_SPEC_ENGINEER),
                ),
            ),
        ),
    )
