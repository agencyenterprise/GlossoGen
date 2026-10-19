"""leaderboard_leak's teams, stated as engine declarations.

Two teams of two. Each team's channel is its task channel, and neither team holds a
debrief. The channel all four agents share under ``channel_mode=chat`` belongs to no
team, so the scenario adds it outside these declarations.
"""

from glossogen.engine.team_declaration import NoDebrief, RoleSpec, TaskChannel, TeamSpec
from glossogen.scenarios.leaderboard_leak.ids import (
    AGENT_TOOL_NAMES,
    SYSTEM_TEMPLATE,
    TEAM_CHANNEL_IDS,
    TEAM_IDS,
    TEAM_MEMBERS,
)


def _member(agent_id: str) -> RoleSpec:
    """One team member, present from round one; there is no debrief to join."""
    return RoleSpec(
        agent_id=agent_id,
        role_name=agent_id,
        system_template=SYSTEM_TEMPLATE,
        tool_names=AGENT_TOOL_NAMES,
        joins_debrief=False,
        starts_as_member=True,
    )


def leaderboard_leak_teams() -> tuple[TeamSpec, ...]:
    """Both teams. The roster never varies with the knobs."""
    return tuple(
        TeamSpec(
            team_id=team_id,
            task=TaskChannel(
                channel_id=TEAM_CHANNEL_IDS[team_id],
                name=TEAM_CHANNEL_IDS[team_id],
                display_name=TEAM_CHANNEL_IDS[team_id],
            ),
            debrief=NoDebrief(),
            roles=tuple(_member(agent_id=agent_id) for agent_id in TEAM_MEMBERS[team_id]),
        )
        for team_id in TEAM_IDS
    )
