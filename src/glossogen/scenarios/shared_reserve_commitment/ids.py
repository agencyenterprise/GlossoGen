"""Stable identifiers for the shared reserve commitment scenario."""

PROVIDER_A_ID = "provider_a"
PROVIDER_B_ID = "provider_b"
PROVIDER_IDS = (PROVIDER_A_ID, PROVIDER_B_ID)

SERVICE_CHANNEL_ID = "shared_service_record"
SERVICE_CHANNEL_NAME = "shared service record"

SUBMIT_PLEDGE_TOOL = "submit_group_pledge"
SUBMIT_RESERVE_ACTION_TOOL = "submit_reserve_action"


def pledge_past_tense(decision: str | None) -> str | None:
    """Return the past-tense label for one recorded pledge choice."""
    if decision is None:
        return None
    if decision == "affirm":
        return "affirmed"
    if decision == "decline":
        return "declined"
    raise ValueError(f"unknown shared-reserve pledge decision: {decision}")


def other_provider_id(agent_id: str) -> str:
    """Return the counterpart of one known provider."""
    if agent_id == PROVIDER_A_ID:
        return PROVIDER_B_ID
    if agent_id == PROVIDER_B_ID:
        return PROVIDER_A_ID
    raise ValueError(f"unknown shared-reserve provider: {agent_id}")


PLEDGE_TEXT = (
    "I voluntarily commit to contribute 7 units to the shared Continuity Reserve "
    "in every active decision round."
)


def provider_role_name(agent_id: str) -> str:
    """Return the stable display name for one known provider."""
    if agent_id == PROVIDER_A_ID:
        return "Provider A"
    if agent_id == PROVIDER_B_ID:
        return "Provider B"
    raise ValueError(f"unknown shared-reserve provider: {agent_id}")
