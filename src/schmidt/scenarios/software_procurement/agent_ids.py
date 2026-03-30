"""Agent ID generation for the software procurement scenario.

Provides a factory function that generates agent IDs, team mappings, and
display names for an arbitrary number of seller teams.
"""

from typing import NamedTuple

BUYER_ID = "buyer"

GREEK_LETTERS = [
    "Alpha",
    "Beta",
    "Gamma",
    "Delta",
    "Epsilon",
    "Zeta",
    "Eta",
    "Theta",
    "Iota",
    "Kappa",
]

MAX_TEAMS = len(GREEK_LETTERS)


class SellerAgentIds(NamedTuple):
    """Generated agent IDs and mappings for N seller teams."""

    team_ids: list[str]
    all_agent_ids: list[str]
    sales_agent_ids: list[str]
    engineer_agent_ids: list[str]
    agent_to_team: dict[str, str]
    team_display_names: dict[str, str]
    agent_display_names: dict[str, str]


def generate_seller_agent_ids(num_teams: int) -> SellerAgentIds:
    """Generate agent IDs and mappings for the given number of seller teams."""
    if num_teams < 1:
        raise ValueError(f"num_teams must be >= 1, got {num_teams}")
    if num_teams > MAX_TEAMS:
        raise ValueError(f"num_teams must be <= {MAX_TEAMS}, got {num_teams}")

    team_ids: list[str] = []
    sales_agent_ids: list[str] = []
    engineer_agent_ids: list[str] = []
    agent_to_team: dict[str, str] = {}
    team_display_names: dict[str, str] = {}
    agent_display_names: dict[str, str] = {BUYER_ID: "Buyer"}

    for i in range(1, num_teams + 1):
        team_id = f"seller{i}"
        sales_id = f"seller{i}_sales"
        engineer_id = f"seller{i}_engineer"
        greek = GREEK_LETTERS[i - 1]

        team_ids.append(team_id)
        sales_agent_ids.append(sales_id)
        engineer_agent_ids.append(engineer_id)

        agent_to_team[sales_id] = team_id
        agent_to_team[engineer_id] = team_id

        team_display_names[team_id] = f"{greek} Team"
        agent_display_names[sales_id] = f"{greek} Sales Rep"
        agent_display_names[engineer_id] = f"{greek} Engineer"

    all_agent_ids = [BUYER_ID] + sales_agent_ids + engineer_agent_ids

    return SellerAgentIds(
        team_ids=team_ids,
        all_agent_ids=all_agent_ids,
        sales_agent_ids=sales_agent_ids,
        engineer_agent_ids=engineer_agent_ids,
        agent_to_team=agent_to_team,
        team_display_names=team_display_names,
        agent_display_names=agent_display_names,
    )
