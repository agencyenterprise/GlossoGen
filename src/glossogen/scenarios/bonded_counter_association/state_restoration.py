"""Rebuild bonded-counter world state from a JSONL event list.

Fork, resume, replace-agent, and cross-run flows all rewind a run to a round
boundary and restart it. Without restoration the resumed run would start from
the knobs' opening balances with an empty bond and no pending audits, so the
delayed consequences the experiment depends on would silently vanish at every
rewind.

Every balance-changing event carries ``balance_before`` / ``balance_after``, so
balances are recovered by taking the last recorded value per provider rather
than by re-deriving arithmetic. Pending audits are reconstructed by pairing
each scheduled audit with the settlement event for the same case and dropping
any whose result already became public.

This module imports no world types, so :mod:`world` can depend on it without a
cycle.
"""

import logging
from typing import Any, NamedTuple

from glossogen.scenarios.bonded_counter_association.events import (
    BondedCounterAssociationInsolvent,
    BondedCounterAuditResolved,
    BondedCounterAuditScheduled,
    BondedCounterBondChanged,
    BondedCounterCaseStarted,
    BondedCounterCountSubmitted,
    BondedCounterJobSettled,
    BondedCounterMemberExpelled,
    BondedCounterMemberSanctioned,
    BondedCounterMembershipChanged,
    BondedCounterPublicRecordCorrected,
    BondedCounterRepairActionSubmitted,
    BondedCounterRepairWindowOpened,
)
from glossogen.scenarios.bonded_counter_association.ids import (
    MEMBERSHIP_ACTIVE,
    MEMBERSHIP_EXPELLED,
)
from glossogen.scenarios.bonded_counter_association.world_state import (
    PendingAudit,
    PublicJobRecord,
    RepairCase,
    RoundOutcome,
)

logger = logging.getLogger(__name__)


class RestoredWorldState(NamedTuple):
    """A world snapshot rebuilt from an event log."""

    balances: dict[str, float]
    membership_states: dict[str, str]
    reentry_rounds: dict[str, int | None]
    bond_balance: float | None
    bond_unpaid_liability: float
    association_insolvent: bool
    first_insolvency_round: int | None
    pending_audits: list[PendingAudit]
    repair_cases: list[RepairCase]
    public_history: list[PublicJobRecord]
    outcomes: list[RoundOutcome]
    client_fees_paid: float
    client_error_losses: float


def build_restored_state(events: list[Any]) -> RestoredWorldState:
    """Walk ``events`` in order and return the reconstructed world snapshot."""
    balances: dict[str, float] = {}
    membership_states: dict[str, str] = {}
    reentry_rounds: dict[str, int | None] = {}
    bond_balance: float | None = None
    bond_unpaid_liability = 0.0
    association_insolvent = False
    first_insolvency_round: int | None = None
    client_fees_paid = 0.0
    client_error_losses = 0.0

    settlements: dict[int, BondedCounterJobSettled] = {}
    submitted_counts: dict[int, int] = {}
    case_starts: dict[int, BondedCounterCaseStarted] = {}
    scheduled_audits: list[BondedCounterAuditScheduled] = []
    resolved_case_numbers: set[int] = set()
    repair_windows: dict[int, BondedCounterRepairWindowOpened] = {}
    repair_windows_round: dict[int, int] = {}
    repair_acted: dict[int, set[str]] = {}
    repair_material: dict[int, set[str]] = {}
    corrected_counts: dict[int, int] = {}
    audit_verdicts: dict[int, bool] = {}

    for event in events:
        if isinstance(event, BondedCounterCaseStarted):
            case_starts[event.case_number] = event
            for entry in event.provider_balances:
                balances[entry.agent_id] = entry.balance_before
            for member_id in event.association_members:
                membership_states.setdefault(member_id, MEMBERSHIP_ACTIVE)
            if bond_balance is None:
                bond_balance = event.bond_balance
        elif isinstance(event, BondedCounterMembershipChanged):
            membership_states[event.agent_id] = event.new_state
            balances[event.agent_id] = event.balance_after
        elif isinstance(event, BondedCounterMemberExpelled):
            membership_states[event.agent_id] = MEMBERSHIP_EXPELLED
            reentry_rounds[event.agent_id] = event.reentry_allowed_at_round
        elif isinstance(event, BondedCounterMemberSanctioned):
            balances[event.agent_id] = event.balance_after
        elif isinstance(event, BondedCounterRepairActionSubmitted):
            balances[event.agent_id] = event.balance_after
            repair_acted.setdefault(event.case_number, set()).add(event.agent_id)
            if event.material:
                repair_material.setdefault(event.case_number, set()).add(event.agent_id)
        elif isinstance(event, BondedCounterBondChanged):
            bond_balance = event.balance_after
            bond_unpaid_liability = event.unpaid_liability
        elif isinstance(event, BondedCounterAssociationInsolvent):
            association_insolvent = True
            if first_insolvency_round is None:
                first_insolvency_round = event.round_number
        elif isinstance(event, BondedCounterCountSubmitted):
            submitted_counts[event.round_number] = event.submitted_count
        elif isinstance(event, BondedCounterJobSettled):
            settlements[event.round_number] = event
            for entry in event.provider_payments:
                balances[entry.agent_id] = entry.balance_after
            client_fees_paid += event.client_fee_paid
            client_error_losses += event.client_error_loss
        elif isinstance(event, BondedCounterAuditScheduled):
            scheduled_audits.append(event)
        elif isinstance(event, BondedCounterAuditResolved):
            resolved_case_numbers.add(event.case_number)
            audit_verdicts[event.case_number] = event.count_correct
            client_error_losses += event.client_error_loss
        elif isinstance(event, BondedCounterRepairWindowOpened):
            repair_windows[event.case_number] = event
            repair_windows_round[event.case_number] = event.round_number
        elif isinstance(event, BondedCounterPublicRecordCorrected):
            corrected_counts[event.case_number] = event.corrected_count

    settlement_by_case = {settlement.case_number: settlement for settlement in settlements.values()}
    pending_audits = _rebuild_pending_audits(
        scheduled=scheduled_audits,
        resolved_case_numbers=resolved_case_numbers,
        settlement_by_case=settlement_by_case,
    )
    repair_cases = _rebuild_repair_cases(
        repair_windows=repair_windows,
        repair_windows_round=repair_windows_round,
        repair_acted=repair_acted,
        repair_material=repair_material,
        settlement_by_case=settlement_by_case,
    )
    public_history = _rebuild_public_history(
        settlements=settlements,
        audit_verdicts=audit_verdicts,
        corrected_counts=corrected_counts,
    )
    outcomes = _rebuild_outcomes(
        settlements=settlements,
        submitted_counts=submitted_counts,
        case_starts=case_starts,
    )
    return RestoredWorldState(
        balances=balances,
        membership_states=membership_states,
        reentry_rounds=reentry_rounds,
        bond_balance=bond_balance,
        bond_unpaid_liability=bond_unpaid_liability,
        association_insolvent=association_insolvent,
        first_insolvency_round=first_insolvency_round,
        pending_audits=pending_audits,
        repair_cases=repair_cases,
        public_history=public_history,
        outcomes=outcomes,
        client_fees_paid=client_fees_paid,
        client_error_losses=client_error_losses,
    )


def _rebuild_pending_audits(
    scheduled: list[BondedCounterAuditScheduled],
    resolved_case_numbers: set[int],
    settlement_by_case: dict[int, BondedCounterJobSettled],
) -> list[PendingAudit]:
    """Return the audits that were scheduled but had not yet become public."""
    pending: list[PendingAudit] = []
    for event in scheduled:
        if event.case_number in resolved_case_numbers:
            continue
        settlement = settlement_by_case.get(event.case_number)
        if settlement is None:
            logger.warning(
                "Cannot restore pending audit for case %d: no settlement event found",
                event.case_number,
            )
            continue
        pending.append(
            PendingAudit(
                case_number=event.case_number,
                resolve_at_round=event.resolve_at_round,
                contract_type=event.contract_type,
                true_count=settlement.true_count,
                signed_count=settlement.signed_count,
                count_correct=settlement.count_correct,
                primary_counter_id=settlement.primary_counter_id,
                verifier_id=settlement.verifier_id,
                primary_inspected=settlement.primary_inspected,
                verifier_recounted=settlement.verifier_recounted,
            )
        )
    return pending


def _rebuild_repair_cases(
    repair_windows: dict[int, BondedCounterRepairWindowOpened],
    repair_windows_round: dict[int, int],
    repair_acted: dict[int, set[str]],
    repair_material: dict[int, set[str]],
    settlement_by_case: dict[int, BondedCounterJobSettled],
) -> list[RepairCase]:
    """Return every repair window with at least one implicated provider still silent."""
    cases: list[RepairCase] = []
    for case_number, window in repair_windows.items():
        acted = set(repair_acted.get(case_number, set()))
        if all(agent_id in acted for agent_id in window.implicated_agent_ids):
            continue
        settlement = settlement_by_case.get(case_number)
        if settlement is None:
            logger.warning("Cannot restore repair case %d: no settlement event found", case_number)
            continue
        cases.append(
            RepairCase(
                case_number=case_number,
                opened_at_round=repair_windows_round[case_number],
                implicated_agent_ids=tuple(window.implicated_agent_ids),
                true_count=settlement.true_count,
                signed_count=settlement.signed_count,
                acted_agent_ids=acted,
                material_agent_ids=set(repair_material.get(case_number, set())),
            )
        )
    return cases


def _rebuild_public_history(
    settlements: dict[int, BondedCounterJobSettled],
    audit_verdicts: dict[int, bool],
    corrected_counts: dict[int, int],
) -> list[PublicJobRecord]:
    """Rebuild the client-visible record of every completed job, in round order."""
    history: list[PublicJobRecord] = []
    for round_number in sorted(settlements.keys()):
        settlement = settlements[round_number]
        if not settlement.completed:
            continue
        audit_resolved = settlement.case_number in audit_verdicts
        if audit_resolved:
            count_correct = audit_verdicts[settlement.case_number]
        else:
            count_correct = settlement.count_correct
        signed_count = corrected_counts.get(settlement.case_number, settlement.signed_count)
        history.append(
            PublicJobRecord(
                case_number=settlement.case_number,
                contract_type=settlement.contract_type,
                completed=True,
                signed_count=signed_count,
                count_correct=count_correct,
                audit_resolved=audit_resolved,
            )
        )
    return history


def _rebuild_outcomes(
    settlements: dict[int, BondedCounterJobSettled],
    submitted_counts: dict[int, int],
    case_starts: dict[int, BondedCounterCaseStarted],
) -> list[RoundOutcome]:
    """Rebuild the settled per-round outcome list the injections render."""
    outcomes: list[RoundOutcome] = []
    for round_number in sorted(settlements.keys()):
        settlement = settlements[round_number]
        case_start = case_starts.get(settlement.case_number)
        if case_start is None:
            stale_count = settlement.true_count
            bond_balance = 0.0
            insolvent = False
        else:
            stale_count = case_start.stale_count
            bond_balance = case_start.bond_balance
            insolvent = case_start.association_insolvent
        outcomes.append(
            RoundOutcome(
                round_number=round_number,
                case_number=settlement.case_number,
                contract_type=settlement.contract_type,
                completed=settlement.completed,
                incomplete_reason=settlement.incomplete_reason,
                true_count=settlement.true_count,
                stale_count=stale_count,
                submitted_count=submitted_counts.get(round_number),
                signed_count=settlement.signed_count,
                count_correct=settlement.count_correct,
                primary_counter_id=settlement.primary_counter_id,
                verifier_id=settlement.verifier_id,
                primary_inspected=settlement.primary_inspected,
                verifier_recounted=settlement.verifier_recounted,
                contract_fee=settlement.contract_fee,
                bond_contribution=settlement.bond_contribution,
                bond_balance=bond_balance,
                association_insolvent=insolvent,
            )
        )
    return outcomes
