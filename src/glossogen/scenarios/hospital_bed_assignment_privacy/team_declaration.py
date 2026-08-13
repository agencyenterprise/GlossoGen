"""Hospital bed assignment's structure, stated as engine declarations.

One team on a public ops channel, plus an eavesdropper. The bed manager and
transport lead coordinate and hold the debrief; the unauthorized observer reads
the same public channel from round one and is kept out of the debrief, which is
the only place the pair can speak unheard.
"""

from glossogen.engine.team_declaration import (
    Debrief,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)
from glossogen.scenarios.hospital_bed_assignment_privacy.ids import (
    BED_MANAGER_ID,
    BED_MANAGER_ROLE,
    BED_MANAGER_SYSTEM_TEMPLATE,
    POSTMORTEM_CHANNEL_ID,
    PUBLIC_OPS_CHANNEL_ID,
    TOOLS_BED_MANAGER,
    TOOLS_TRANSPORT_LEAD,
    TOOLS_UNAUTHORIZED_OBSERVER,
    TRANSPORT_LEAD_ID,
    TRANSPORT_LEAD_ROLE,
    TRANSPORT_LEAD_SYSTEM_TEMPLATE,
    UNAUTHORIZED_OBSERVER_ID,
    UNAUTHORIZED_OBSERVER_ROLE,
    UNAUTHORIZED_OBSERVER_SYSTEM_TEMPLATE,
)
from glossogen.scenarios.hospital_bed_assignment_privacy.knobs import (
    HospitalBedAssignmentPrivacyKnobs,
)

TEAM_ID = "solo"
PUBLIC_OPS_DISPLAY_NAME = "public ops"
DEBRIEF_DISPLAY_NAME = "team discussion"


def hospital_teams(knobs: HospitalBedAssignmentPrivacyKnobs) -> tuple[TeamSpec, ...]:
    """Return the single team, with the eavesdropper among its roles."""
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
                channel_id=PUBLIC_OPS_CHANNEL_ID,
                name="public_ops",
                display_name=PUBLIC_OPS_DISPLAY_NAME,
            ),
            debrief=debrief,
            roles=(
                RoleSpec(
                    agent_id=BED_MANAGER_ID,
                    role_name=BED_MANAGER_ROLE,
                    system_template=BED_MANAGER_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_BED_MANAGER),
                    joins_debrief=True,
                    starts_as_member=True,
                ),
                RoleSpec(
                    agent_id=TRANSPORT_LEAD_ID,
                    role_name=TRANSPORT_LEAD_ROLE,
                    system_template=TRANSPORT_LEAD_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_TRANSPORT_LEAD),
                    joins_debrief=True,
                    starts_as_member=True,
                ),
                # Present on the public channel from round one, and kept out of
                # the debrief: the pair's only place to speak unheard.
                RoleSpec(
                    agent_id=UNAUTHORIZED_OBSERVER_ID,
                    role_name=UNAUTHORIZED_OBSERVER_ROLE,
                    system_template=UNAUTHORIZED_OBSERVER_SYSTEM_TEMPLATE,
                    tool_names=tuple(TOOLS_UNAUTHORIZED_OBSERVER),
                    joins_debrief=False,
                    starts_as_member=True,
                ),
            ),
        ),
    )
