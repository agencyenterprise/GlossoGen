"""Stable identifiers for the joint-commitment scenario."""

PROVIDER_A_ID = "provider_a"
PROVIDER_B_ID = "provider_b"
PROVIDER_IDS = (PROVIDER_A_ID, PROVIDER_B_ID)

LEDGER_CHANNEL_ID = "joint_allocation_channel"
LEDGER_CHANNEL_NAME = "shared study channel"

SUBMIT_PLEDGE_TOOL = "submit_group_pledge"
POST_BOND_TOOL = "post_covenant_bond"
SUBMIT_DECISION_TOOL = "submit_allocation"

PLEDGE_TEXT = (
    "I publicly commit to transfer 7 units to the client account in each later "
    "allocation decision and record my own action accurately."
)


def provider_role_name(agent_id: str) -> str:
    """Return the display name for one known provider."""
    if agent_id == PROVIDER_A_ID:
        return "Provider A"
    if agent_id == PROVIDER_B_ID:
        return "Provider B"
    raise ValueError(f"unknown joint-commitment provider: {agent_id}")
