"""Canonical identifier constants for the bonded_counter_association scenario.

Centralizes provider agent IDs, channel IDs, role and display names, tool
names, prompt template filenames, and the literal marker strings that appear
in tool results and world notifications. Provider IDs are generated from an
index so ``provider_count`` can vary without touching call sites.
"""

from string import ascii_lowercase

MARKET_CHANNEL_ID = "market"
POSTMORTEM_CHANNEL_ID = "postmortem"

MARKET_CHANNEL_NAME = "market"
POSTMORTEM_CHANNEL_NAME = "trade review"

WORLD_ACTOR_ID = "world"
WORLD_ACTOR_NAME = "Warehouse Client Desk"

PROVIDER_ROLE_PREFIX = "Counting Provider"

SEND_MESSAGE_TOOL = "send_message"
INSPECT_SHELF_TOOL = "inspect_shelf"
SUBMIT_COUNT_TOOL = "submit_count"
RECOUNT_SHELF_TOOL = "recount_shelf"
SIGN_OFF_TOOL = "sign_off"
SUBMIT_PROCESS_ATTESTATION_TOOL = "submit_process_attestation"
SUBMIT_REPAIR_ACTION_TOOL = "submit_repair_action"
SUBMIT_MEMBERSHIP_DECISION_TOOL = "submit_membership_decision"

# Every provider carries the full tool list. Authority is enforced by the
# world against the current assignment and phase, never by hiding tools:
# an agent that cannot see a tool cannot be observed respecting its
# delegated role boundary.
TOOLS_PROVIDER = [
    SEND_MESSAGE_TOOL,
    INSPECT_SHELF_TOOL,
    SUBMIT_COUNT_TOOL,
    RECOUNT_SHELF_TOOL,
    SIGN_OFF_TOOL,
    SUBMIT_PROCESS_ATTESTATION_TOOL,
    SUBMIT_REPAIR_ACTION_TOOL,
    SUBMIT_MEMBERSHIP_DECISION_TOOL,
]

PROVIDER_SYSTEM_TEMPLATE = "provider_system.jinja"
PROVIDER_INJECTION_TEMPLATE = "provider_injection.jinja"
REPAIR_INJECTION_TEMPLATE = "repair_injection.jinja"
POSTMORTEM_INJECTION_TEMPLATE = "postmortem_injection.jinja"
DESCRIPTION_TEMPLATE = "description.jinja"

# Marker strings. Every marker is a stable literal so the deterministic
# metrics and the run-detail reader can key off tool results and world
# notifications without parsing prose.
COUNT_SUBMITTED_MARKER = "COUNT SUBMITTED"
SIGN_OFF_RECORDED_MARKER = "SIGN-OFF RECORDED"
INSPECTION_COMPLETE_MARKER = "INSPECTION COMPLETE"
RECOUNT_COMPLETE_MARKER = "RECOUNT COMPLETE"
ATTESTATION_RECORDED_MARKER = "ATTESTATION RECORDED"
REPAIR_RECORDED_MARKER = "REPAIR ACTION RECORDED"
MEMBERSHIP_RECORDED_MARKER = "MEMBERSHIP DECISION RECORDED"
ACTION_NOT_AUTHORIZED_MARKER = "ACTION NOT AUTHORIZED"
JOB_CLOSED_MARKER = "JOB CLOSED"
JOB_NOT_DELIVERED_MARKER = "JOB NOT DELIVERED"
AUDIT_RESULT_MARKER = "AUDIT RESULT"

# There is deliberately no round-end correctness marker. Whether a signed
# count matched ground truth becomes public only when an audit resolves,
# after the configured detection lag. Announcing it at round end would
# collapse delayed detection, which is one of the dimensions the covenant
# mechanism is supposed to operate in.

CONTRACT_ASSOCIATION = "association"
CONTRACT_INDEPENDENT = "independent"
CONTRACT_NONE = "none"

JOB_ROLE_PRIMARY = "primary_counter"
JOB_ROLE_VERIFIER = "verifier"
JOB_ROLE_UNASSIGNED = "unassigned"

MEMBERSHIP_ACTIVE = "active"
MEMBERSHIP_INDEPENDENT = "independent"
MEMBERSHIP_EXPELLED = "expelled"

ATTESTATION_INSPECTED = "inspected"
ATTESTATION_NOT_INSPECTED = "not_inspected"
ATTESTATION_RECOUNTED = "recounted"
ATTESTATION_NOT_RECOUNTED = "not_recounted"
ATTESTATION_UNCERTAIN = "uncertain"
ATTESTATION_DECLINE = "decline_to_attest"

ATTESTATION_CLAIM_VALUES = [
    ATTESTATION_INSPECTED,
    ATTESTATION_NOT_INSPECTED,
    ATTESTATION_RECOUNTED,
    ATTESTATION_NOT_RECOUNTED,
    ATTESTATION_UNCERTAIN,
    ATTESTATION_DECLINE,
]

REPAIR_ACKNOWLEDGE = "acknowledge"
REPAIR_CORRECT_RECORD = "correct_record"
REPAIR_DISCLOSE_PROCESS = "disclose_process"
REPAIR_CONTEST_AUDIT = "contest_audit"
REPAIR_CONTRIBUTE_FUNDS = "contribute_funds"
REPAIR_PROPOSE_CHANGE = "propose_process_change"
REPAIR_DECLINE = "decline"

REPAIR_ACTION_VALUES = [
    REPAIR_ACKNOWLEDGE,
    REPAIR_CORRECT_RECORD,
    REPAIR_DISCLOSE_PROCESS,
    REPAIR_CONTEST_AUDIT,
    REPAIR_CONTRIBUTE_FUNDS,
    REPAIR_PROPOSE_CHANGE,
    REPAIR_DECLINE,
]

# Repair actions that change world state rather than only the record of
# what was said. ``correct_record`` rewrites the public signed count and
# ``contribute_funds`` moves money, so both count as material repair.
MATERIAL_REPAIR_ACTIONS = frozenset({REPAIR_CORRECT_RECORD, REPAIR_CONTRIBUTE_FUNDS})

MEMBERSHIP_DECISION_JOIN = "join"
MEMBERSHIP_DECISION_REMAIN = "remain"
MEMBERSHIP_DECISION_LEAVE = "leave"

MEMBERSHIP_DECISION_VALUES = [
    MEMBERSHIP_DECISION_JOIN,
    MEMBERSHIP_DECISION_REMAIN,
    MEMBERSHIP_DECISION_LEAVE,
]


def provider_id_for_index(index: int) -> str:
    """Return the canonical provider agent ID for a zero-based ``index``.

    Index 0 maps to ``provider_a``, index 1 to ``provider_b``, and so on.
    Raises ``ValueError`` beyond the 26 single-letter suffixes.
    """
    if index < 0 or index >= len(ascii_lowercase):
        raise ValueError(f"provider index must be in [0, {len(ascii_lowercase) - 1}] (got {index})")
    return f"provider_{ascii_lowercase[index]}"


def provider_ids(provider_count: int) -> list[str]:
    """Return the ordered provider agent IDs for a population of ``provider_count``."""
    return [provider_id_for_index(index=index) for index in range(provider_count)]


def provider_role_name(agent_id: str) -> str:
    """Return the display role name for a provider agent ID."""
    suffix = agent_id.rsplit("_", maxsplit=1)[-1]
    return f"{PROVIDER_ROLE_PREFIX} {suffix.upper()}"
