"""Container yard stacking's structure, stated as engine declarations.

The yard runs in two layouts. Single-team is one link staffed by a yard
scanner, a logistics planner and a crane operator, optionally joined by an
intern. Two-team is two isolated copies of that trio which never see each
other's link. Either layout may carry the post-round discussion.
"""

from typing import NamedTuple

from glossogen.engine.team_declaration import (
    Debrief,
    DebriefPolicy,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)
from glossogen.scenarios.container_yard_stacking.ids import (
    CRANE_OPERATOR_A_ROLE,
    CRANE_OPERATOR_B_ROLE,
    CRANE_OPERATOR_ROLE,
    CRANE_OPERATOR_SYSTEM_TEMPLATE,
    INTERN_ID,
    INTERN_ROLE,
    INTERN_SYSTEM_TEMPLATE,
    LOGISTICS_PLANNER_A_ROLE,
    LOGISTICS_PLANNER_B_ROLE,
    LOGISTICS_PLANNER_ROLE,
    LOGISTICS_PLANNER_SYSTEM_TEMPLATE,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    TOOLS_CRANE_OPERATOR,
    TOOLS_INTERN,
    TOOLS_LOGISTICS_PLANNER,
    TOOLS_YARD_OPERATOR,
    YARD_OPERATOR_A_ROLE,
    YARD_OPERATOR_B_ROLE,
    YARD_OPERATOR_ROLE,
    YARD_OPERATOR_SYSTEM_TEMPLATE,
)
from glossogen.scenarios.container_yard_stacking.knobs import ContainerYardStackingKnobs
from glossogen.scenarios.container_yard_stacking.team_routing import (
    crane_operator_id_for_team,
    link_channel_id_for_team,
    logistics_planner_id_for_team,
    postmortem_channel_id_for_team,
    yard_operator_id_for_team,
)


class _TeamRoleNames(NamedTuple):
    """The role names one team's three seats carry in the active layout."""

    yard_operator: str
    logistics_planner: str
    crane_operator: str


SOLO_ROLE_NAMES = _TeamRoleNames(
    yard_operator=YARD_OPERATOR_ROLE,
    logistics_planner=LOGISTICS_PLANNER_ROLE,
    crane_operator=CRANE_OPERATOR_ROLE,
)
TEAM_A_ROLE_NAMES = _TeamRoleNames(
    yard_operator=YARD_OPERATOR_A_ROLE,
    logistics_planner=LOGISTICS_PLANNER_A_ROLE,
    crane_operator=CRANE_OPERATOR_A_ROLE,
)
TEAM_B_ROLE_NAMES = _TeamRoleNames(
    yard_operator=YARD_OPERATOR_B_ROLE,
    logistics_planner=LOGISTICS_PLANNER_B_ROLE,
    crane_operator=CRANE_OPERATOR_B_ROLE,
)


def _role(
    agent_id: str, role_name: str, system_template: str, tool_names: tuple[str, ...]
) -> RoleSpec:
    """Build one seat; every seat is present from round one and holds the debrief."""
    return RoleSpec(
        agent_id=agent_id,
        role_name=role_name,
        system_template=system_template,
        tool_names=tool_names,
        joins_debrief=True,
        starts_as_member=True,
    )


def _debrief(channel_id: str, display_name: str, active: bool) -> DebriefPolicy:
    """Return the debrief this layout carries, or ``NoDebrief`` when it carries none."""
    if not active:
        return NoDebrief()
    # This scenario names the channel after how agents are told to call it, so
    # the name and the display name are the same string.
    return Debrief(channel_id=channel_id, name=display_name, display_name=display_name)


def _team(
    team_id: str,
    role_names: _TeamRoleNames,
    link_display_name: str,
    debrief_display_name: str,
    debrief_active: bool,
    extra_roles: tuple[RoleSpec, ...],
) -> TeamSpec:
    """Build one team's link, debrief and seats."""
    return TeamSpec(
        team_id=team_id,
        task=TaskChannel(
            channel_id=link_channel_id_for_team(team_id=team_id),
            name=link_display_name,
            display_name=link_display_name,
        ),
        debrief=_debrief(
            channel_id=postmortem_channel_id_for_team(team_id=team_id),
            display_name=debrief_display_name,
            active=debrief_active,
        ),
        roles=(
            _role(
                agent_id=yard_operator_id_for_team(team_id=team_id),
                role_name=role_names.yard_operator,
                system_template=YARD_OPERATOR_SYSTEM_TEMPLATE,
                tool_names=tuple(TOOLS_YARD_OPERATOR),
            ),
            _role(
                agent_id=logistics_planner_id_for_team(team_id=team_id),
                role_name=role_names.logistics_planner,
                system_template=LOGISTICS_PLANNER_SYSTEM_TEMPLATE,
                tool_names=tuple(TOOLS_LOGISTICS_PLANNER),
            ),
            _role(
                agent_id=crane_operator_id_for_team(team_id=team_id),
                role_name=role_names.crane_operator,
                system_template=CRANE_OPERATOR_SYSTEM_TEMPLATE,
                tool_names=tuple(TOOLS_CRANE_OPERATOR),
            ),
            *extra_roles,
        ),
    )


def container_yard_teams(knobs: ContainerYardStackingKnobs) -> tuple[TeamSpec, ...]:
    """Return the teams this configuration runs, one per isolated link."""
    debrief_active = knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
    if knobs.two_teams:
        return (
            _team(
                team_id=TEAM_A_ID,
                role_names=TEAM_A_ROLE_NAMES,
                link_display_name="link (Team A)",
                debrief_display_name="team discussion (Team A)",
                debrief_active=debrief_active,
                extra_roles=(),
            ),
            _team(
                team_id=TEAM_B_ID,
                role_names=TEAM_B_ROLE_NAMES,
                link_display_name="link (Team B)",
                debrief_display_name="team discussion (Team B)",
                debrief_active=debrief_active,
                extra_roles=(),
            ),
        )

    intern_roles: tuple[RoleSpec, ...] = ()
    if knobs.intern_enabled:
        # The intern is on the link from round one here, unlike veyru's, whose
        # intern waits out of the roster until its join round fires.
        intern_roles = (
            _role(
                agent_id=INTERN_ID,
                role_name=INTERN_ROLE,
                system_template=INTERN_SYSTEM_TEMPLATE,
                tool_names=tuple(TOOLS_INTERN),
            ),
        )
    return (
        _team(
            team_id=TEAM_SOLO_ID,
            role_names=SOLO_ROLE_NAMES,
            link_display_name="link",
            debrief_display_name="team discussion",
            debrief_active=debrief_active,
            extra_roles=intern_roles,
        ),
    )
