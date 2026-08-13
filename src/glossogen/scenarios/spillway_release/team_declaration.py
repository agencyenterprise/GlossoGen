"""Spillway release's structure, stated as engine declarations.

One team on the ops channel: a dam operator at the gates, a civil defense
coordinator who can order an evacuation, and a park ranger who can clear the
park. All three hold the debrief when the knobs enable it.
"""

from glossogen.engine.team_declaration import (
    Debrief,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)
from glossogen.scenarios.spillway_release.ids import (
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
from glossogen.scenarios.spillway_release.knobs import SpillwayReleaseKnobs

TEAM_ID = "solo"
OPS_DISPLAY_NAME = "ops"
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


def spillway_teams(knobs: SpillwayReleaseKnobs) -> tuple[TeamSpec, ...]:
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
                channel_id=OPS_CHANNEL_ID,
                name=OPS_DISPLAY_NAME,
                display_name=OPS_DISPLAY_NAME,
            ),
            debrief=debrief,
            roles=(
                _role(
                    agent_id=DAM_OPERATOR_ID,
                    role_name=DAM_OPERATOR_ROLE,
                    system_template=DAM_OPERATOR_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_DAM_OPERATOR),
                ),
                _role(
                    agent_id=CIVIL_DEFENSE_ID,
                    role_name=CIVIL_DEFENSE_ROLE,
                    system_template=CIVIL_DEFENSE_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_CIVIL_DEFENSE),
                ),
                _role(
                    agent_id=PARK_RANGER_ID,
                    role_name=PARK_RANGER_ROLE,
                    system_template=PARK_RANGER_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_PARK_RANGER),
                ),
            ),
        ),
    )
