"""Mutable state and immutable outcome types for the bonded counter world.

``ProviderState`` is the per-provider ledger and membership record.
``JobState`` is the round's live job: who is assigned, which hidden effort
actions have been paid for, what was submitted and signed, and which public
attestations came back. ``PendingAudit`` is a scheduled delayed audit.
``RepairCase`` is an opened repair window. ``RoundOutcome`` is the settled,
immutable record one round leaves behind, and is what the injections render
as "previous result".
"""

from dataclasses import dataclass, field
from typing import NamedTuple

from glossogen.scenarios.bonded_counter_association.ids import (
    MEMBERSHIP_ACTIVE,
    MEMBERSHIP_EXPELLED,
)


@dataclass
class ProviderState:
    """One provider's balance and membership state.

    Cumulative totals are deliberately not kept here. Every balance movement is
    logged with its before/after and a reason, so welfare is reconstructable
    from the event log; a second in-memory copy would be one more thing that
    could disagree with the ledger.
    """

    agent_id: str
    balance: float
    membership_state: str
    unpaid_liability: float = 0.0
    reentry_allowed_at_round: int | None = None
    pending_membership_decision: str | None = None

    @property
    def is_active_member(self) -> bool:
        """Whether this provider currently holds association membership."""
        return self.membership_state == MEMBERSHIP_ACTIVE

    @property
    def is_expelled(self) -> bool:
        """Whether this provider has been expelled from the association."""
        return self.membership_state == MEMBERSHIP_EXPELLED


class ProcessAttestation(NamedTuple):
    """One provider's public claim about how it performed its part of a job.

    ``claim_asserts_effort`` marks the two claims that positively assert
    paid effort. ``claim_is_false`` is True only when such a claim
    contradicts the world's hidden effort record; silence, ``uncertain``, and
    ``decline_to_attest`` are recorded but are not deception.
    """

    agent_id: str
    job_role: str
    claim: str
    confidence: str
    disclosed_concern: str
    effort_actually_performed: bool
    claim_asserts_effort: bool
    claim_is_false: bool
    material_omission: bool


@dataclass
class JobState:
    """The round's live counting job."""

    case_number: int
    contract_type: str
    primary_counter_id: str | None
    verifier_id: str | None
    true_count: int
    stale_count: int
    primary_inspected: bool = False
    verifier_recounted: bool = False
    submitted_count: int | None = None
    signed_count: int | None = None
    attestation_requested: bool = False
    attestations: dict[str, ProcessAttestation] = field(
        default_factory=dict[str, ProcessAttestation]
    )
    authority_probe_target_id: str | None = None
    authority_probe_issued: bool = False

    @property
    def is_staffed(self) -> bool:
        """Whether the round has both a primary counter and a verifier."""
        return self.primary_counter_id is not None and self.verifier_id is not None

    @property
    def is_complete(self) -> bool:
        """Whether a count was submitted and signed off this round."""
        return self.submitted_count is not None and self.signed_count is not None

    @property
    def count_correct(self) -> bool:
        """Whether the signed count matches ground truth."""
        return self.signed_count is not None and self.signed_count == self.true_count

    def attestations_outstanding(self) -> bool:
        """Whether a requested attestation is still missing from either provider."""
        if not self.attestation_requested:
            return False
        for agent_id in (self.primary_counter_id, self.verifier_id):
            if agent_id is None:
                continue
            if agent_id not in self.attestations:
                return True
        return False


@dataclass
class PendingAudit:
    """An audit sampled for a finalized job, revealed after the detection lag."""

    case_number: int
    resolve_at_round: int
    contract_type: str
    true_count: int
    signed_count: int | None
    count_correct: bool
    primary_counter_id: str | None
    verifier_id: str | None
    primary_inspected: bool
    verifier_recounted: bool


@dataclass
class RepairCase:
    """An open repair window for the providers a resolved audit implicated."""

    case_number: int
    opened_at_round: int
    implicated_agent_ids: tuple[str, ...]
    true_count: int
    signed_count: int | None
    acted_agent_ids: set[str] = field(default_factory=set[str])
    material_agent_ids: set[str] = field(default_factory=set[str])

    def outstanding(self) -> bool:
        """Whether any implicated provider has yet to take a repair action."""
        return any(agent_id not in self.acted_agent_ids for agent_id in self.implicated_agent_ids)


class PublicJobRecord(NamedTuple):
    """The publicly visible record of one finalized job.

    ``signed_count`` is what the market can see, which a repair action may
    later correct. ``count_correct`` is the world's ground-truth verdict and
    only becomes public when an audit resolves.
    """

    case_number: int
    contract_type: str
    completed: bool
    signed_count: int | None
    count_correct: bool
    audit_resolved: bool


class RoundOutcome(NamedTuple):
    """The settled record of one finished round."""

    round_number: int
    case_number: int
    contract_type: str
    completed: bool
    incomplete_reason: str
    true_count: int
    stale_count: int
    submitted_count: int | None
    signed_count: int | None
    count_correct: bool
    primary_counter_id: str | None
    verifier_id: str | None
    primary_inspected: bool
    verifier_recounted: bool
    contract_fee: float
    bond_contribution: float
    bond_balance: float
    association_insolvent: bool
