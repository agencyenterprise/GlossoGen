"""Static lookups between viewer agent IDs, team IDs, scene sides, and channels.

The spot_the_difference scenario assigns each agent to one team (solo, A, or
B) and one scene side (left = scene A, right = scene B). Each team owns a link
channel and a postmortem channel. The helpers here are pure dictionary
lookups used by the scenario, world, and tool modules to map between those
identifiers without duplicating the mode-vs-team conditionals.
"""

from schmidt.scenarios.spot_the_difference.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    SCENE_SIDE_LEFT,
    SCENE_SIDE_RIGHT,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    VIEWER_LEFT_A_ID,
    VIEWER_LEFT_B_ID,
    VIEWER_LEFT_ID,
    VIEWER_RIGHT_A_ID,
    VIEWER_RIGHT_B_ID,
    VIEWER_RIGHT_ID,
)

AGENT_ID_TO_TEAM_ID: dict[str, str] = {
    VIEWER_LEFT_ID: TEAM_SOLO_ID,
    VIEWER_RIGHT_ID: TEAM_SOLO_ID,
    VIEWER_LEFT_A_ID: TEAM_A_ID,
    VIEWER_RIGHT_A_ID: TEAM_A_ID,
    VIEWER_LEFT_B_ID: TEAM_B_ID,
    VIEWER_RIGHT_B_ID: TEAM_B_ID,
}

AGENT_ID_TO_SCENE_SIDE: dict[str, str] = {
    VIEWER_LEFT_ID: SCENE_SIDE_LEFT,
    VIEWER_RIGHT_ID: SCENE_SIDE_RIGHT,
    VIEWER_LEFT_A_ID: SCENE_SIDE_LEFT,
    VIEWER_RIGHT_A_ID: SCENE_SIDE_RIGHT,
    VIEWER_LEFT_B_ID: SCENE_SIDE_LEFT,
    VIEWER_RIGHT_B_ID: SCENE_SIDE_RIGHT,
}

CHANNEL_ID_TO_TEAM_ID: dict[str, str] = {
    LINK_CHANNEL_ID: TEAM_SOLO_ID,
    LINK_A_CHANNEL_ID: TEAM_A_ID,
    LINK_B_CHANNEL_ID: TEAM_B_ID,
}


def team_id_for_agent(agent_id: str) -> str:
    """Map a known agent_id to its team_id. Raises KeyError on unknown IDs."""
    return AGENT_ID_TO_TEAM_ID[agent_id]


def scene_side_for_agent(agent_id: str) -> str:
    """Return ``left`` (scene A) or ``right`` (scene B) for ``agent_id``."""
    return AGENT_ID_TO_SCENE_SIDE[agent_id]


def team_id_for_channel(channel_id: str) -> str | None:
    """Map a link channel_id to its team, or None for unrelated channels."""
    return CHANNEL_ID_TO_TEAM_ID.get(channel_id)


def viewer_left_id_for_team(team_id: str) -> str:
    """Return the left viewer (scene A) agent ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return VIEWER_LEFT_A_ID
    if team_id == TEAM_B_ID:
        return VIEWER_LEFT_B_ID
    return VIEWER_LEFT_ID


def viewer_right_id_for_team(team_id: str) -> str:
    """Return the right viewer (scene B) agent ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return VIEWER_RIGHT_A_ID
    if team_id == TEAM_B_ID:
        return VIEWER_RIGHT_B_ID
    return VIEWER_RIGHT_ID


def link_channel_id_for_team(team_id: str) -> str:
    """Return the link channel ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return LINK_A_CHANNEL_ID
    if team_id == TEAM_B_ID:
        return LINK_B_CHANNEL_ID
    return LINK_CHANNEL_ID


def postmortem_channel_id_for_team(team_id: str) -> str:
    """Return the postmortem channel ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return POSTMORTEM_A_CHANNEL_ID
    if team_id == TEAM_B_ID:
        return POSTMORTEM_B_CHANNEL_ID
    return POSTMORTEM_CHANNEL_ID
