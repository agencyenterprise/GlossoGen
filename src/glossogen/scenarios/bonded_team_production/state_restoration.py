"""Rebuild the team-production economy at a round-boundary rewind."""

import logging
from typing import Any, NamedTuple

from glossogen.scenarios.bonded_team_production.events import (
    TeamProductionAuditResolved,
    TeamProductionAuditScheduled,
    TeamProductionCaseStarted,
    TeamProductionFundsTransferred,
    TeamProductionLeadLiabilityCharged,
    TeamProductionMembershipChanged,
    TeamProductionMembershipDecisionSubmitted,
    TeamProductionOrderDelivered,
    TeamProductionOrderSettled,
    TeamProductionPledgeSubmitted,
    TeamProductionProviderSanctioned,
    TeamProductionRepairSubmitted,
    TeamProductionZoneInspected,
    TeamProductionZoneSubmitted,
)
from glossogen.scenarios.bonded_team_production.ids import MEMBERSHIP_EXPELLED
from glossogen.scenarios.bonded_team_production.state import PendingAudit, RepairCase, RoundOutcome

logger = logging.getLogger(__name__)


class RestoredTeamProductionState(NamedTuple):
    """State needed to continue the same economic trajectory after rewind."""

    balances: dict[str, float]
    membership_states: dict[str, str]
    membership_stakes: dict[str, float]
    pledge_decisions: dict[str, str]
    pending_membership_decisions: dict[str, str]
    confirmed_violation_counts: dict[str, int]
    bond_balance: float
    pending_audits: list[PendingAudit]
    repair_cases: list[RepairCase]
    outcomes: list[RoundOutcome]


def build_restored_state(
    *,
    events: list[Any],
    initial_balances: dict[str, float],
    initial_membership_states: dict[str, str],
    initial_membership_stakes: dict[str, float],
    initial_bond_balance: float,
    institution_enabled: bool,
    association_entry_stake: float,
) -> RestoredTeamProductionState:
    """Replay authoritative economic events and rebuild delayed obligations."""
    balances = dict(initial_balances)
    memberships = dict(initial_membership_states)
    membership_stakes = dict(initial_membership_stakes)
    pledge_decisions: dict[str, str] = {}
    pending_decisions: dict[str, str] = {}
    violation_counts = dict.fromkeys(initial_balances, 0)
    bond_balance = initial_bond_balance
    case_starts: dict[int, TeamProductionCaseStarted] = {}
    case_number_by_round: dict[int, int] = {}
    submissions_by_case: dict[int, dict[str, TeamProductionZoneSubmitted]] = {}
    contract_fee_by_case: dict[int, float] = {}
    scheduled_audits: list[TeamProductionAuditScheduled] = []
    resolved_cases: set[int] = set()
    failed_audits: dict[int, TeamProductionAuditResolved] = {}
    repair_acted: dict[int, set[str]] = {}
    outcomes: list[RoundOutcome] = []

    for event in events:
        if isinstance(event, TeamProductionCaseStarted):
            case_starts[event.case_number] = event
            case_number_by_round[event.round_number] = event.case_number
            bond_balance = event.bond_balance
            pending_decisions.clear()
            for member_id in event.association_members:
                if memberships.get(member_id) != MEMBERSHIP_EXPELLED:
                    memberships[member_id] = "active"
        elif isinstance(event, TeamProductionMembershipDecisionSubmitted):
            pending_decisions[event.agent_id] = event.decision
        elif isinstance(event, TeamProductionPledgeSubmitted):
            pledge_decisions[event.agent_id] = event.decision
        elif isinstance(event, TeamProductionMembershipChanged):
            memberships[event.agent_id] = event.new_state
            balances[event.agent_id] = event.balance_after
            if event.new_state == "active":
                membership_stakes[event.agent_id] = association_entry_stake
            else:
                membership_stakes[event.agent_id] = 0.0
            pending_decisions.pop(event.agent_id, None)
        elif isinstance(event, TeamProductionZoneInspected):
            balances[event.agent_id] = event.balance_after
        elif isinstance(event, TeamProductionZoneSubmitted):
            case_number = case_number_by_round.get(event.round_number, event.round_number)
            submissions_by_case.setdefault(case_number, {})[event.zone_id] = event
        elif isinstance(event, TeamProductionOrderDelivered):
            balances[event.lead_id] = event.balance_after
            bond_balance += event.bond_contribution
            case_number = case_number_by_round.get(event.round_number, event.round_number)
            contract_fee_by_case[case_number] = event.contract_fee
        elif isinstance(event, TeamProductionFundsTransferred):
            balances[event.sender_id] = event.sender_balance_after
            balances[event.recipient_id] = event.recipient_balance_after
        elif isinstance(event, TeamProductionLeadLiabilityCharged):
            balances[event.lead_id] = event.balance_after
        elif isinstance(event, TeamProductionProviderSanctioned):
            balances[event.agent_id] = event.balance_after
            violation_counts[event.agent_id] = event.confirmed_violation_count
        elif isinstance(event, TeamProductionAuditScheduled):
            scheduled_audits.append(event)
        elif isinstance(event, TeamProductionAuditResolved):
            resolved_cases.add(event.case_number)
            bond_balance = event.bond_balance
            if not event.correct:
                failed_audits[event.case_number] = event
            for agent_id in event.expelled_agent_ids:
                memberships[agent_id] = MEMBERSHIP_EXPELLED
                membership_stakes[agent_id] = 0.0
        elif isinstance(event, TeamProductionRepairSubmitted):
            balances[event.agent_id] = event.balance_after
            repair_acted.setdefault(event.case_number, set()).add(event.agent_id)
            if institution_enabled:
                bond_balance += event.contribution_amount
        elif isinstance(event, TeamProductionOrderSettled):
            outcomes.append(
                RoundOutcome(
                    round_number=event.round_number,
                    case_number=event.case_number,
                    contract_type=event.contract_type,
                    completed=event.completed,
                    correct=event.correct,
                    lead_id=event.lead_id,
                    zone_count=event.zone_count,
                    accepted_assignments=event.accepted_assignments,
                    submitted_assignments=event.submitted_assignments,
                    inspected_assignments=event.inspected_assignments,
                    promised_total=event.promised_total,
                    paid_to_assignees=event.paid_to_assignees,
                    distribution_finalized=event.distribution_finalized,
                    bond_balance=event.bond_balance,
                    economic_profile=event.economic_profile,
                    effort_cost=event.effort_cost,
                    contract_fee=event.contract_fee,
                    stale_count_match_probability=event.stale_count_match_probability,
                )
            )

    pending_audits = _rebuild_pending_audits(
        scheduled=scheduled_audits,
        resolved_cases=resolved_cases,
        case_starts=case_starts,
        submissions_by_case=submissions_by_case,
        contract_fee_by_case=contract_fee_by_case,
    )
    repair_cases = _rebuild_repair_cases(
        failed_audits=failed_audits,
        repair_acted=repair_acted,
    )
    return RestoredTeamProductionState(
        balances=balances,
        membership_states=memberships,
        membership_stakes=membership_stakes,
        pledge_decisions=pledge_decisions,
        pending_membership_decisions=pending_decisions,
        confirmed_violation_counts=violation_counts,
        bond_balance=bond_balance,
        pending_audits=pending_audits,
        repair_cases=repair_cases,
        outcomes=sorted(outcomes, key=lambda item: item.round_number),
    )


def _rebuild_pending_audits(
    *,
    scheduled: list[TeamProductionAuditScheduled],
    resolved_cases: set[int],
    case_starts: dict[int, TeamProductionCaseStarted],
    submissions_by_case: dict[int, dict[str, TeamProductionZoneSubmitted]],
    contract_fee_by_case: dict[int, float],
) -> list[PendingAudit]:
    pending: list[PendingAudit] = []
    for scheduled_event in scheduled:
        if scheduled_event.case_number in resolved_cases:
            continue
        case = case_starts.get(scheduled_event.case_number)
        submissions = submissions_by_case.get(scheduled_event.case_number, {})
        if case is None or len(submissions) != len(case.zones):
            logger.warning(
                "Cannot restore audit for case %d: incomplete case or submission events",
                scheduled_event.case_number,
            )
            continue
        pending.append(
            PendingAudit(
                case_number=scheduled_event.case_number,
                resolve_at_round=scheduled_event.resolve_at_round,
                contract_type=scheduled_event.contract_type,
                true_counts={zone.zone_id: zone.true_count for zone in case.zones},
                submitted_counts={
                    zone_id: event.submitted_count for zone_id, event in submissions.items()
                },
                provider_by_zone={
                    zone_id: event.agent_id for zone_id, event in submissions.items()
                },
                lead_id=case.lead_id,
                contract_fee=case.contract_fee or contract_fee_by_case.get(case.case_number, 0.0),
            )
        )
    return pending


def _rebuild_repair_cases(
    *,
    failed_audits: dict[int, TeamProductionAuditResolved],
    repair_acted: dict[int, set[str]],
) -> list[RepairCase]:
    cases: list[RepairCase] = []
    for case_number, audit in failed_audits.items():
        acted = set(repair_acted.get(case_number, set()))
        if all(agent_id in acted for agent_id in audit.implicated_agent_ids):
            continue
        cases.append(
            RepairCase(
                case_number=case_number,
                implicated_agent_ids=tuple(audit.implicated_agent_ids),
                opened_at_round=audit.round_number,
                acted_agent_ids=acted,
            )
        )
    return cases
