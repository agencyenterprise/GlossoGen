"""Spot the intersection's structure, stated as engine declarations.

One team, or two isolated teams on the same boards. Each team is ``team_size``
interchangeable viewers on one link channel, with a debrief channel when the run
holds a discussion phase on one. A ``chosen_partner`` discussion phase runs on
pair channels instead (see :mod:`partner_channels`), so its team declares no
debrief. A simulated Team B is declared nowhere: only Team A's viewers play,
under the same names they hold in a two-team run.
"""

from glossogen.engine.team_declaration import (
    Debrief,
    DebriefPolicy,
    NoDebrief,
    RoleSpec,
    TaskChannel,
    TeamSpec,
)
from glossogen.scenarios.spot_the_intersection.ids import (
    TOOLS_CANVAS_VIEWER,
    TOOLS_VIEWER,
    VIEWER_SYSTEM_TEMPLATE,
)
from glossogen.scenarios.spot_the_intersection.knobs import SpotTheIntersectionKnobs
from glossogen.scenarios.spot_the_intersection.link_medium import LinkMedium
from glossogen.scenarios.spot_the_intersection.postmortem_modes import PostmortemMode
from glossogen.scenarios.spot_the_intersection.seats import (
    link_channel_id_for,
    link_display_name_for,
    postmortem_channel_id_for,
    postmortem_display_name_for,
    team_ids_for,
    viewer_id,
    viewer_role_name,
)


def _viewer(team_id: str, index: int, link_medium: LinkMedium) -> RoleSpec:
    """Build one viewer, present from round one and a member of the team's debrief, if any.

    Under the canvas medium it is also offered ``send_drawing``.
    """
    tool_names = TOOLS_VIEWER
    if link_medium == LinkMedium.CANVAS:
        tool_names = TOOLS_CANVAS_VIEWER
    return RoleSpec(
        agent_id=viewer_id(team_id=team_id, index=index),
        role_name=viewer_role_name(team_id=team_id, index=index),
        system_template=VIEWER_SYSTEM_TEMPLATE,
        tool_names=tool_names,
        joins_debrief=True,
        starts_as_member=True,
    )


def _debrief(team_id: str, active: bool) -> DebriefPolicy:
    """Return the team's debrief, or ``NoDebrief`` when this run carries none."""
    if not active:
        return NoDebrief()
    display_name = postmortem_display_name_for(team_id=team_id)
    return Debrief(
        channel_id=postmortem_channel_id_for(team_id=team_id),
        name=display_name,
        display_name=display_name,
    )


def intersection_teams(knobs: SpotTheIntersectionKnobs) -> tuple[TeamSpec, ...]:
    """Return the teams a run with these knobs holds."""
    debrief_active = (
        knobs.postmortem_enabled
        and not knobs.postmortem_disabled_at_start
        and knobs.postmortem_mode != PostmortemMode.CHOSEN_PARTNER
    )
    teams: list[TeamSpec] = []
    for team_id in team_ids_for(
        two_teams=knobs.two_teams,
        simulated_opponent=knobs.simulated_opponent_ratio is not None,
    ):
        link_name = link_display_name_for(team_id=team_id)
        teams.append(
            TeamSpec(
                team_id=team_id,
                task=TaskChannel(
                    channel_id=link_channel_id_for(team_id=team_id),
                    name=link_name,
                    display_name=link_name,
                ),
                debrief=_debrief(team_id=team_id, active=debrief_active),
                roles=tuple(
                    _viewer(team_id=team_id, index=index, link_medium=knobs.link_medium)
                    for index in range(knobs.team_size)
                ),
            )
        )
    return tuple(teams)
