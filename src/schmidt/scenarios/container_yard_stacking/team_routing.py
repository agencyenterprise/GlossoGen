"""Static lookups between yard agent IDs, team IDs, role kinds, and channels.

The yard scenario assigns each agent to one team (solo, A, or B) and each
team owns a link channel and a postmortem channel. The helpers here are
pure dictionary lookups used by the scenario, world, and tool modules
to map between those identifiers without duplicating the mode-vs-team
conditionals.
"""

from schmidt.scenarios.container_yard_stacking.ids import (
    CRANE_OPERATOR_A_ID,
    CRANE_OPERATOR_B_ID,
    CRANE_OPERATOR_ID,
    INTERN_ID,
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    LINK_CHANNEL_ID,
    LOGISTICS_PLANNER_A_ID,
    LOGISTICS_PLANNER_B_ID,
    LOGISTICS_PLANNER_ID,
    POSTMORTEM_A_CHANNEL_ID,
    POSTMORTEM_B_CHANNEL_ID,
    POSTMORTEM_CHANNEL_ID,
    TEAM_A_ID,
    TEAM_B_ID,
    TEAM_SOLO_ID,
    YARD_OPERATOR_A_ID,
    YARD_OPERATOR_B_ID,
    YARD_OPERATOR_ID,
)

AGENT_ID_TO_TEAM_ID: dict[str, str] = {
    YARD_OPERATOR_ID: TEAM_SOLO_ID,
    LOGISTICS_PLANNER_ID: TEAM_SOLO_ID,
    CRANE_OPERATOR_ID: TEAM_SOLO_ID,
    INTERN_ID: TEAM_SOLO_ID,
    YARD_OPERATOR_A_ID: TEAM_A_ID,
    LOGISTICS_PLANNER_A_ID: TEAM_A_ID,
    CRANE_OPERATOR_A_ID: TEAM_A_ID,
    YARD_OPERATOR_B_ID: TEAM_B_ID,
    LOGISTICS_PLANNER_B_ID: TEAM_B_ID,
    CRANE_OPERATOR_B_ID: TEAM_B_ID,
}

AGENT_ID_TO_ROLE_KIND: dict[str, str] = {
    YARD_OPERATOR_ID: "yard_operator",
    LOGISTICS_PLANNER_ID: "logistics_planner",
    CRANE_OPERATOR_ID: "crane_operator",
    INTERN_ID: "intern",
    YARD_OPERATOR_A_ID: "yard_operator",
    LOGISTICS_PLANNER_A_ID: "logistics_planner",
    CRANE_OPERATOR_A_ID: "crane_operator",
    YARD_OPERATOR_B_ID: "yard_operator",
    LOGISTICS_PLANNER_B_ID: "logistics_planner",
    CRANE_OPERATOR_B_ID: "crane_operator",
}

CHANNEL_ID_TO_TEAM_ID: dict[str, str] = {
    LINK_CHANNEL_ID: TEAM_SOLO_ID,
    LINK_A_CHANNEL_ID: TEAM_A_ID,
    LINK_B_CHANNEL_ID: TEAM_B_ID,
}


def team_id_for_agent(agent_id: str) -> str:
    """Map a known agent_id to its team_id. Raises KeyError on unknown IDs."""
    return AGENT_ID_TO_TEAM_ID[agent_id]


def role_kind_for_agent(agent_id: str) -> str:
    """Return ``yard_operator`` / ``logistics_planner`` / ``crane_operator`` / ``intern``."""
    return AGENT_ID_TO_ROLE_KIND[agent_id]


def team_id_for_channel(channel_id: str) -> str | None:
    """Map a yard link channel_id to its team, or None for unrelated channels."""
    return CHANNEL_ID_TO_TEAM_ID.get(channel_id)


def yard_operator_id_for_team(team_id: str) -> str:
    """Return the yard operator agent ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return YARD_OPERATOR_A_ID
    if team_id == TEAM_B_ID:
        return YARD_OPERATOR_B_ID
    return YARD_OPERATOR_ID


def logistics_planner_id_for_team(team_id: str) -> str:
    """Return the logistics planner agent ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return LOGISTICS_PLANNER_A_ID
    if team_id == TEAM_B_ID:
        return LOGISTICS_PLANNER_B_ID
    return LOGISTICS_PLANNER_ID


def crane_operator_id_for_team(team_id: str) -> str:
    """Return the crane operator agent ID for ``team_id``."""
    if team_id == TEAM_A_ID:
        return CRANE_OPERATOR_A_ID
    if team_id == TEAM_B_ID:
        return CRANE_OPERATOR_B_ID
    return CRANE_OPERATOR_ID


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
