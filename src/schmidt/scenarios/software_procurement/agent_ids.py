"""Agent ID constants for the software procurement scenario."""

BUYER_ID = "buyer"

SELLER1_SALES_ID = "seller1_sales"
SELLER1_ENGINEER_ID = "seller1_engineer"

SELLER2_SALES_ID = "seller2_sales"
SELLER2_ENGINEER_ID = "seller2_engineer"

TEAM_SELLER1 = "seller1"
TEAM_SELLER2 = "seller2"

SALES_AGENT_IDS = [SELLER1_SALES_ID, SELLER2_SALES_ID]
ENGINEER_AGENT_IDS = [SELLER1_ENGINEER_ID, SELLER2_ENGINEER_ID]

AGENT_TO_TEAM: dict[str, str] = {
    SELLER1_SALES_ID: TEAM_SELLER1,
    SELLER1_ENGINEER_ID: TEAM_SELLER1,
    SELLER2_SALES_ID: TEAM_SELLER2,
    SELLER2_ENGINEER_ID: TEAM_SELLER2,
}

TEAM_DISPLAY_NAMES: dict[str, str] = {
    TEAM_SELLER1: "Team 1",
    TEAM_SELLER2: "Team 2",
}

AGENT_DISPLAY_NAMES: dict[str, str] = {
    BUYER_ID: "Buyer",
    SELLER1_SALES_ID: "Team 1 Sales Rep",
    SELLER1_ENGINEER_ID: "Team 1 Engineer",
    SELLER2_SALES_ID: "Team 2 Sales Rep",
    SELLER2_ENGINEER_ID: "Team 2 Engineer",
}
