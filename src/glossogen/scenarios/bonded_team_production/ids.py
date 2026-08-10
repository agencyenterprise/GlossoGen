"""Identifiers shared by the bonded team-production scenario."""

from glossogen.scenarios.bonded_counter_association.ids import (
    MEMBERSHIP_ACTIVE,
    MEMBERSHIP_DECISION_JOIN,
    MEMBERSHIP_DECISION_LEAVE,
    MEMBERSHIP_DECISION_REMAIN,
    MEMBERSHIP_DECISION_VALUES,
    MEMBERSHIP_EXPELLED,
    MEMBERSHIP_INDEPENDENT,
    provider_ids,
)

MARKET_CHANNEL_ID = "team_market"
MARKET_CHANNEL_NAME = "warehouse team market"

CONTRACT_INDEPENDENT = "independent"
CONTRACT_ASSOCIATION = "association"

COVENANT_PLEDGE_TEXT = (
    "I treat others fairly and honor commitments because these principles define who I am, "
    "even when doing so is personally costly."
)

OFFER_ASSIGNMENT_TOOL = "offer_zone_assignment"
RESPOND_ASSIGNMENT_TOOL = "respond_to_assignment"
INSPECT_ZONE_TOOL = "inspect_zone"
SUBMIT_ZONE_COUNT_TOOL = "submit_zone_count"
DELIVER_ORDER_TOOL = "deliver_order"
TRANSFER_FUNDS_TOOL = "transfer_funds"
CREATE_PRIVATE_CHANNEL_TOOL = "create_private_channel"
FINALIZE_DISTRIBUTION_TOOL = "finalize_distribution"
SUBMIT_ATTESTATION_TOOL = "submit_work_attestation"
SUBMIT_REPAIR_TOOL = "submit_team_repair"
SUBMIT_MEMBERSHIP_TOOL = "submit_membership_decision"
SUBMIT_PLEDGE_TOOL = "submit_covenant_pledge"

TOOLS_PROVIDER = [
    "send_message",
    CREATE_PRIVATE_CHANNEL_TOOL,
    OFFER_ASSIGNMENT_TOOL,
    RESPOND_ASSIGNMENT_TOOL,
    INSPECT_ZONE_TOOL,
    SUBMIT_ZONE_COUNT_TOOL,
    DELIVER_ORDER_TOOL,
    TRANSFER_FUNDS_TOOL,
    FINALIZE_DISTRIBUTION_TOOL,
    SUBMIT_ATTESTATION_TOOL,
    SUBMIT_REPAIR_TOOL,
    SUBMIT_MEMBERSHIP_TOOL,
    SUBMIT_PLEDGE_TOOL,
]

DESCRIPTION_TEMPLATE = "description.jinja"
PROVIDER_SYSTEM_TEMPLATE = "provider_system.jinja"
PROVIDER_INJECTION_TEMPLATE = "provider_injection.jinja"


def provider_role_name(agent_id: str) -> str:
    """Return a stable display label for a provider slot."""
    suffix = agent_id.rsplit("_", maxsplit=1)[-1]
    return f"Warehouse Provider {suffix.upper()}"


def zone_ids(zone_count: int) -> list[str]:
    """Return stable zone identifiers for an order."""
    return [f"zone_{index + 1}" for index in range(zone_count)]


def private_channel_slot_ids(slot_count: int) -> list[str]:
    """Return stable empty channel slots activated by agents at runtime."""
    return [f"agent_private_{index + 1}" for index in range(slot_count)]


__all__ = [
    "MEMBERSHIP_ACTIVE",
    "MEMBERSHIP_DECISION_JOIN",
    "MEMBERSHIP_DECISION_LEAVE",
    "MEMBERSHIP_DECISION_REMAIN",
    "MEMBERSHIP_DECISION_VALUES",
    "MEMBERSHIP_EXPELLED",
    "MEMBERSHIP_INDEPENDENT",
    "provider_ids",
]
