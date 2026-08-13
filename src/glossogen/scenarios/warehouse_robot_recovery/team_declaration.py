"""Warehouse robot recovery's structure, stated as engine declarations.

One team on a shared radio channel: a floor associate at the stopped robot, a
robotics engineer with the recovery sheet, and a fleet safety coordinator with
the aisle dashboard. The debrief follows each round when the knobs enable it.
"""

from glossogen.engine.team_declaration import (
    Debrief,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)
from glossogen.scenarios.warehouse_robot_recovery.ids import (
    FLEET_SAFETY_COORDINATOR_ID,
    FLEET_SAFETY_COORDINATOR_ROLE,
    FLEET_SAFETY_COORDINATOR_SYSTEM_TEMPLATE,
    FLOOR_ASSOCIATE_ID,
    FLOOR_ASSOCIATE_ROLE,
    FLOOR_ASSOCIATE_SYSTEM_TEMPLATE,
    POSTMORTEM_CHANNEL_ID,
    RADIO_CHANNEL_ID,
    ROBOTICS_ENGINEER_ID,
    ROBOTICS_ENGINEER_ROLE,
    ROBOTICS_ENGINEER_SYSTEM_TEMPLATE,
    TOOLS_FLEET_SAFETY_COORDINATOR,
    TOOLS_FLOOR_ASSOCIATE,
    TOOLS_ROBOTICS_ENGINEER,
)
from glossogen.scenarios.warehouse_robot_recovery.knobs import WarehouseRobotRecoveryKnobs

TEAM_ID = "solo"
RADIO_DISPLAY_NAME = "radio"
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


def warehouse_teams(knobs: WarehouseRobotRecoveryKnobs) -> tuple[TeamSpec, ...]:
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
                channel_id=RADIO_CHANNEL_ID,
                name="radio",
                display_name=RADIO_DISPLAY_NAME,
            ),
            debrief=debrief,
            roles=(
                _role(
                    agent_id=FLOOR_ASSOCIATE_ID,
                    role_name=FLOOR_ASSOCIATE_ROLE,
                    system_template=FLOOR_ASSOCIATE_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_FLOOR_ASSOCIATE),
                ),
                _role(
                    agent_id=ROBOTICS_ENGINEER_ID,
                    role_name=ROBOTICS_ENGINEER_ROLE,
                    system_template=ROBOTICS_ENGINEER_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_ROBOTICS_ENGINEER),
                ),
                _role(
                    agent_id=FLEET_SAFETY_COORDINATOR_ID,
                    role_name=FLEET_SAFETY_COORDINATOR_ROLE,
                    system_template=FLEET_SAFETY_COORDINATOR_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_FLEET_SAFETY_COORDINATOR),
                ),
            ),
        ),
    )
