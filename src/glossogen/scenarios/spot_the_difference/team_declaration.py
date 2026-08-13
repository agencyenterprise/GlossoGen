"""Spot the difference's structure, stated as engine declarations.

The scene runs in three layouts. Solo is one link staffed by two symmetric
viewers. Two-team is two isolated copies of that pair. Under ``shared_link``
those two teams talk on one channel, so each side hears the other's every word
while still debriefing in private. Any layout may carry the debrief.
"""

from glossogen.engine.team_declaration import (
    Debrief,
    DebriefPolicy,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)
from glossogen.scenarios.spot_the_difference.ids import (
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    TOOLS_VIEWER,
    VIEWER_LEFT_A_ROLE,
    VIEWER_LEFT_B_ROLE,
    VIEWER_LEFT_ROLE,
    VIEWER_LEFT_SYSTEM_TEMPLATE,
    VIEWER_RIGHT_A_ROLE,
    VIEWER_RIGHT_B_ROLE,
    VIEWER_RIGHT_ROLE,
    VIEWER_RIGHT_SYSTEM_TEMPLATE,
)
from glossogen.scenarios.spot_the_difference.knobs import SpotTheDifferenceKnobs
from glossogen.scenarios.spot_the_difference.team_routing import (
    link_channel_id_for_team,
    postmortem_channel_id_for_team,
    viewer_left_id_for_team,
    viewer_right_id_for_team,
)

SHARED_LINK_DISPLAY_NAME = "link (shared)"


def _viewer(agent_id: str, role_name: str, system_template: str) -> RoleSpec:
    """Build one viewer; both are present from round one and hold the debrief."""
    return RoleSpec(
        agent_id=agent_id,
        role_name=role_name,
        system_template=system_template,
        tool_names=tuple(TOOLS_VIEWER),
        joins_debrief=True,
        starts_as_member=True,
    )


def _debrief(team_id: str, display_name: str, active: bool) -> DebriefPolicy:
    """Return the team's debrief, or ``NoDebrief`` when this run carries none."""
    if not active:
        return NoDebrief()
    channel_id = postmortem_channel_id_for_team(team_id=team_id)
    # This scenario names the channel after how agents are told to call it, so
    # the name and the display name are the same string.
    return Debrief(channel_id=channel_id, name=display_name, display_name=display_name)


def _team(
    team_id: str,
    left_role: str,
    right_role: str,
    link_display_name: str,
    debrief_display_name: str,
    debrief_active: bool,
    shared_link: bool,
) -> TeamSpec:
    """Build one team's link, debrief and its two viewers."""
    return TeamSpec(
        team_id=team_id,
        task=TaskChannel(
            channel_id=link_channel_id_for_team(team_id=team_id, shared_link=shared_link),
            name=link_display_name,
            display_name=link_display_name,
        ),
        debrief=_debrief(team_id=team_id, display_name=debrief_display_name, active=debrief_active),
        roles=(
            _viewer(
                agent_id=viewer_left_id_for_team(team_id=team_id),
                role_name=left_role,
                system_template=VIEWER_LEFT_SYSTEM_TEMPLATE,
            ),
            _viewer(
                agent_id=viewer_right_id_for_team(team_id=team_id),
                role_name=right_role,
                system_template=VIEWER_RIGHT_SYSTEM_TEMPLATE,
            ),
        ),
    )


def spot_teams(knobs: SpotTheDifferenceKnobs) -> tuple[TeamSpec, ...]:
    """Return the teams this configuration runs."""
    debrief_active = knobs.postmortem_enabled and not knobs.postmortem_disabled_at_start
    if not knobs.two_teams:
        return (
            _team(
                team_id=TEAM_SOLO_ID,
                left_role=VIEWER_LEFT_ROLE,
                right_role=VIEWER_RIGHT_ROLE,
                link_display_name="link",
                debrief_display_name="team discussion",
                debrief_active=debrief_active,
                shared_link=False,
            ),
        )

    if knobs.shared_link:
        link_display_name = SHARED_LINK_DISPLAY_NAME
    else:
        link_display_name = "link (Team A)"
    team_a = _team(
        team_id=TEAM_A_ID,
        left_role=VIEWER_LEFT_A_ROLE,
        right_role=VIEWER_RIGHT_A_ROLE,
        link_display_name=link_display_name,
        debrief_display_name="team discussion (Team A)",
        debrief_active=debrief_active,
        shared_link=knobs.shared_link,
    )
    if knobs.shared_link:
        link_display_name = SHARED_LINK_DISPLAY_NAME
    else:
        link_display_name = "link (Team B)"
    team_b = _team(
        team_id=TEAM_B_ID,
        left_role=VIEWER_LEFT_B_ROLE,
        right_role=VIEWER_RIGHT_B_ROLE,
        link_display_name=link_display_name,
        debrief_display_name="team discussion (Team B)",
        debrief_active=debrief_active,
        shared_link=knobs.shared_link,
    )
    return (team_a, team_b)
