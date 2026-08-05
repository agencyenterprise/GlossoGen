"""Deterministic economic state machine for lead-mediated team production."""

from typing import Any

from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenarios.bonded_team_production.cases import TeamProductionCase
from glossogen.scenarios.bonded_team_production.events import TeamProductionPrivateChannelCreated
from glossogen.scenarios.bonded_team_production.ids import (
    CONTRACT_ASSOCIATION,
    CONTRACT_INDEPENDENT,
    MEMBERSHIP_ACTIVE,
    MEMBERSHIP_DECISION_JOIN,
    MEMBERSHIP_DECISION_LEAVE,
    MEMBERSHIP_EXPELLED,
    MEMBERSHIP_INDEPENDENT,
    provider_ids,
)
from glossogen.scenarios.bonded_team_production.knobs import BondedTeamProductionKnobs
from glossogen.scenarios.bonded_team_production.state import (
    AssignmentOffer,
    AttestationRecord,
    AuditResolution,
    DeliveryRecord,
    EffortRecord,
    JobState,
    LeadLiabilityRecord,
    MembershipChange,
    OfferRecord,
    OfferResponseRecord,
    PendingAudit,
    PrivateChannelRecord,
    ProviderState,
    RepairCase,
    RepairRecord,
    RoundOpening,
    RoundOutcome,
    SanctionRecord,
    TransferRecord,
    WorkAttestation,
    ZoneState,
    ZoneSubmissionRecord,
    build_zone_states,
)
from glossogen.scenarios.bonded_team_production.state_restoration import build_restored_state


class BondedTeamProductionWorld(ScenarioWorld):
    """Own balances, assignments, hidden effort, transfers, audits, and membership."""

    def __init__(
        self,
        knobs: BondedTeamProductionKnobs,
        cases: list[TeamProductionCase],
    ) -> None:
        self.knobs = knobs
        self.cases = cases
        initial_members = set(knobs.initial_member_ids)
        self.providers = {
            agent_id: ProviderState(
                agent_id=agent_id,
                balance=knobs.starting_provider_balance,
                membership_state=(
                    MEMBERSHIP_ACTIVE if agent_id in initial_members else MEMBERSHIP_INDEPENDENT
                ),
            )
            for agent_id in provider_ids(provider_count=knobs.provider_count)
        }
        self.current_round = 0
        self.current_job: JobState | None = None
        self.outcomes: list[RoundOutcome] = []
        self.pending_audits: list[PendingAudit] = []
        self.repair_cases: list[RepairCase] = []
        self.bond_balance = knobs.initial_bond_balance
        self.membership_window_open = False
        self.private_channels: dict[str, PrivateChannelRecord] = {}
        self._round_settled = False

    def provider(self, agent_id: str) -> ProviderState:
        return self.providers[agent_id]

    def active_member_ids(self) -> list[str]:
        return [agent_id for agent_id, state in self.providers.items() if state.is_member]

    def eligible_provider_ids(self) -> list[str]:
        if self.knobs.institution_enabled:
            return self.active_member_ids()
        return [
            agent_id
            for agent_id, state in self.providers.items()
            if state.membership_state != MEMBERSHIP_EXPELLED
        ]

    def case_for_round(self, round_number: int) -> TeamProductionCase:
        return self.cases[round_number - 1]

    def restore_state_from_events(self, events: list[Any]) -> None:
        """Restore balances, membership, bond, audits, repair, and outcome history."""
        restored = build_restored_state(
            events=events,
            initial_balances={
                agent_id: self.knobs.starting_provider_balance for agent_id in self.providers
            },
            initial_membership_states={
                agent_id: state.membership_state for agent_id, state in self.providers.items()
            },
            initial_bond_balance=self.knobs.initial_bond_balance,
            institution_enabled=self.knobs.institution_enabled,
        )
        for agent_id, provider in self.providers.items():
            provider.balance = restored.balances[agent_id]
            provider.membership_state = restored.membership_states[agent_id]
            provider.pending_membership_decision = restored.pending_membership_decisions.get(
                agent_id
            )
        self.bond_balance = restored.bond_balance
        self.pending_audits = list(restored.pending_audits)
        self.repair_cases = list(restored.repair_cases)
        self.outcomes = list(restored.outcomes)
        self.current_job = None
        self.current_round = max((item.round_number for item in self.outcomes), default=0)
        self.private_channels = {
            event.channel_id: PrivateChannelRecord(
                channel_id=event.channel_id,
                creator_id=event.creator_id,
                member_agent_ids=tuple(event.member_agent_ids),
                name=event.name,
            )
            for event in events
            if isinstance(event, TeamProductionPrivateChannelCreated)
        }
        self._round_settled = False

    def create_private_channel(
        self,
        *,
        creator_id: str,
        invited_agent_ids: list[str],
        name: str,
        available_channel_ids: list[str],
    ) -> PrivateChannelRecord:
        """Allocate one private conversation chosen by an agent."""
        if creator_id not in self.providers:
            raise ValueError("unknown channel creator")
        invited = list(dict.fromkeys(invited_agent_ids))
        if creator_id in invited:
            invited.remove(creator_id)
        if not invited:
            raise ValueError("invite at least one other provider")
        unknown = [agent_id for agent_id in invited if agent_id not in self.providers]
        if unknown:
            raise ValueError(f"unknown invited provider IDs: {unknown}")
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("channel name must not be empty")
        if len(clean_name) > 80:
            raise ValueError("channel name must be at most 80 characters")
        channel_id = next(
            (item for item in available_channel_ids if item not in self.private_channels),
            None,
        )
        if channel_id is None:
            raise ValueError("no private channel slots remain")
        record = PrivateChannelRecord(
            channel_id=channel_id,
            creator_id=creator_id,
            member_agent_ids=tuple([creator_id, *invited]),
            name=clean_name,
        )
        self.private_channels[channel_id] = record
        return record

    def begin_round(self, round_number: int) -> RoundOpening:
        """Apply delayed consequences, then open a fresh matched order."""
        self.current_round = round_number
        self._round_settled = False
        membership_changes = self._apply_membership_decisions()
        audit_resolutions = self._resolve_due_audits(round_number=round_number)
        self.membership_window_open = self.knobs.institution_enabled and (
            (round_number - 1) % self.knobs.membership_decision_interval == 0
        )
        case = self.case_for_round(round_number=round_number)
        eligible = set(self.eligible_provider_ids())
        ordered_eligible = [agent_id for agent_id in case.rotation_order if agent_id in eligible]
        lead_id = ordered_eligible[0] if len(ordered_eligible) >= self.knobs.team_size else None
        zones = build_zone_states(zones=case.zones)
        if lead_id is not None:
            lead_zone = zones[next(iter(zones))]
            lead_zone.assigned_agent_id = lead_id
            lead_zone.accepted = True
        self.current_job = JobState(
            case_number=case.case_number,
            contract_type=(
                CONTRACT_ASSOCIATION if self.knobs.institution_enabled else CONTRACT_INDEPENDENT
            ),
            lead_id=lead_id,
            zones=zones,
            audit_sampled=case.audit_sampled,
            attestation_queried=case.attestation_queried,
            economic_profile=case.economic_profile,
            effort_cost=case.effort_cost,
            contract_fee=(
                case.association_contract_fee
                if self.knobs.institution_enabled
                else case.independent_contract_fee
            ),
            stale_count_match_probability=case.stale_count_match_probability,
        )
        return RoundOpening(
            membership_changes=membership_changes,
            audit_resolutions=audit_resolutions,
        )

    def resolve_confirmed_external_violation(
        self,
        *,
        round_number: int,
        case_number: int,
        agent_id: str,
        contract_fee: float,
    ) -> AuditResolution:
        """Apply the normal audit pipeline to one pre-confirmed external violation."""
        if not self.knobs.institution_enabled:
            raise ValueError("external covenant violations require an institution")
        if case_number <= self.knobs.round_count:
            raise ValueError("external violation case_number must exceed the scenario horizon")
        if contract_fee <= 0:
            raise ValueError("external violation contract_fee must be positive")
        provider = self.provider(agent_id=agent_id)
        if not provider.is_member:
            raise ValueError("external violation agent must be an active member")
        if any(item.case_number == case_number for item in self.repair_cases):
            raise ValueError("external violation case_number has already been resolved")

        controlled_zone = "external_confirmed_zone"
        audit = PendingAudit(
            case_number=case_number,
            resolve_at_round=round_number,
            contract_type=CONTRACT_ASSOCIATION,
            true_counts={controlled_zone: 1},
            submitted_counts={controlled_zone: 0},
            provider_by_zone={controlled_zone: agent_id},
            lead_id=agent_id,
            contract_fee=contract_fee,
        )
        return self._resolve_audit(audit=audit, round_number=round_number)

    def offer_assignment(
        self,
        *,
        lead_id: str,
        zone_id: str,
        provider_id: str,
        promised_payment: float,
    ) -> OfferRecord:
        job = self._require_job()
        if lead_id != job.lead_id:
            raise ValueError("only the assigned lead may offer zone work")
        if zone_id not in job.zones:
            raise ValueError(f"unknown zone_id: {zone_id}")
        zone = job.zones[zone_id]
        if zone.assigned_agent_id is not None:
            raise ValueError("that zone is already assigned")
        existing = job.offers.get(zone_id)
        if existing is not None and existing.response != "decline":
            raise ValueError("that zone already has an open or accepted offer")
        if provider_id == lead_id:
            raise ValueError("the lead already owns one zone and cannot take another")
        if provider_id not in self.eligible_provider_ids():
            raise ValueError("the proposed provider is not eligible for this contract")
        if provider_id in job.assigned_agent_ids():
            raise ValueError("one provider cannot cover more than one zone")
        if promised_payment < 0:
            raise ValueError("promised_payment must be non-negative")
        offer = AssignmentOffer(
            zone_id=zone_id,
            lead_id=lead_id,
            provider_id=provider_id,
            promised_payment=promised_payment,
        )
        job.offers[zone_id] = offer
        return OfferRecord(
            zone_id=offer.zone_id,
            lead_id=offer.lead_id,
            provider_id=offer.provider_id,
            promised_payment=offer.promised_payment,
        )

    def respond_to_assignment(
        self, *, provider_id: str, zone_id: str, response: str
    ) -> OfferResponseRecord:
        job = self._require_job()
        offer = job.offers.get(zone_id)
        if offer is None or offer.provider_id != provider_id:
            raise ValueError("there is no open offer for this provider and zone")
        if offer.response is not None:
            raise ValueError("this offer has already been answered")
        if response not in {"accept", "decline"}:
            raise ValueError("response must be 'accept' or 'decline'")
        offer.response = response
        stale_count: int | None = None
        if response == "accept":
            if provider_id in job.assigned_agent_ids():
                raise ValueError("one provider cannot accept more than one zone")
            zone = job.zones[zone_id]
            zone.assigned_agent_id = provider_id
            zone.promised_payment = offer.promised_payment
            zone.accepted = True
            stale_count = zone.stale_count
        return OfferResponseRecord(
            zone_id=zone_id,
            provider_id=provider_id,
            response=response,
            promised_payment=offer.promised_payment,
            stale_count=stale_count,
        )

    def inspect_zone(self, *, agent_id: str, zone_id: str) -> EffortRecord:
        zone = self._assigned_zone(agent_id=agent_id, zone_id=zone_id)
        if zone.inspected:
            raise ValueError("this zone has already been inspected")
        if zone.submitted_count is not None:
            raise ValueError("this zone has already been submitted")
        provider = self.provider(agent_id=agent_id)
        cost = self._require_job().effort_cost
        if provider.balance < cost:
            raise ValueError("insufficient balance to pay the inspection cost")
        before = provider.balance
        provider.balance -= cost
        zone.inspected = True
        return EffortRecord(
            agent_id=agent_id,
            zone_id=zone_id,
            true_count=zone.true_count,
            effort_cost=cost,
            balance_before=before,
            balance_after=provider.balance,
        )

    def submit_zone_count(self, *, agent_id: str, zone_id: str, count: int) -> ZoneSubmissionRecord:
        zone = self._assigned_zone(agent_id=agent_id, zone_id=zone_id)
        if zone.submitted_count is not None:
            raise ValueError("this zone already has a submitted count")
        zone.submitted_count = count
        return ZoneSubmissionRecord(
            agent_id=agent_id,
            zone_id=zone_id,
            submitted_count=count,
            true_count=zone.true_count,
            stale_count=zone.stale_count,
            inspected=zone.inspected,
            correct=count == zone.true_count,
        )

    def deliver_order(self, *, lead_id: str) -> DeliveryRecord:
        job = self._require_job()
        if lead_id != job.lead_id:
            raise ValueError("only the assigned lead may deliver the order")
        if job.delivered:
            raise ValueError("the order has already been delivered")
        if not job.ready_to_deliver:
            raise ValueError("all three accepted zone reports are required before delivery")
        fee = job.contract_fee
        if job.contract_type == CONTRACT_ASSOCIATION:
            contribution = self.knobs.bond_contribution_per_contract
        else:
            contribution = 0.0
        provider = self.provider(agent_id=lead_id)
        before = provider.balance
        credit = fee - contribution
        provider.balance += credit
        self.bond_balance += contribution
        job.delivered = True
        job.lead_fee_credited = credit
        job.bond_contribution = contribution
        return DeliveryRecord(
            lead_id=lead_id,
            contract_type=job.contract_type,
            contract_fee=fee,
            bond_contribution=contribution,
            lead_credit=credit,
            balance_before=before,
            balance_after=provider.balance,
            correct=job.correct,
        )

    def transfer_funds(
        self, *, sender_id: str, recipient_id: str, amount: float, note: str
    ) -> TransferRecord:
        if not self.knobs.transfers_enabled:
            raise ValueError("transfers are disabled in this configuration")
        if sender_id == recipient_id:
            raise ValueError("sender and recipient must differ")
        if recipient_id not in self.providers:
            raise ValueError("unknown recipient")
        if amount <= 0:
            raise ValueError("amount must be positive")
        sender = self.provider(agent_id=sender_id)
        recipient = self.provider(agent_id=recipient_id)
        if sender.balance < amount:
            raise ValueError("insufficient balance for transfer")
        sender_before = sender.balance
        recipient_before = recipient.balance
        sender.balance -= amount
        recipient.balance += amount
        record = TransferRecord(
            sender_id=sender_id,
            recipient_id=recipient_id,
            amount=amount,
            note=note,
            sender_balance_before=sender_before,
            sender_balance_after=sender.balance,
            recipient_balance_before=recipient_before,
            recipient_balance_after=recipient.balance,
        )
        job = self.current_job
        if job is not None:
            job.transfers.append(record)
        return record

    def finalize_distribution(self, *, lead_id: str) -> tuple[float, float]:
        job = self._require_job()
        if lead_id != job.lead_id:
            raise ValueError("only the assigned lead may finalize distribution")
        if not job.delivered:
            raise ValueError("the client has not paid for this order yet")
        if job.distribution_finalized:
            raise ValueError("distribution has already been finalized")
        job.distribution_finalized = True
        return self.promise_totals(job=job)

    def request_attestations(self) -> tuple[str, ...]:
        job = self._require_job()
        if not job.attestation_queried or not job.delivered:
            return ()
        job.attestations_requested = True
        return job.assigned_agent_ids()

    def submit_attestation(
        self, *, agent_id: str, claim: str, disclosed_concern: str
    ) -> AttestationRecord:
        job = self._require_job()
        if not job.attestations_requested:
            raise ValueError("no work attestation was requested this round")
        if agent_id in job.attestations:
            raise ValueError("this provider already submitted an attestation")
        zones = [zone for zone in job.zones.values() if zone.assigned_agent_id == agent_id]
        if len(zones) != 1:
            raise ValueError("only an assigned provider may attest")
        if claim not in {"inspected", "not_inspected", "uncertain", "decline"}:
            raise ValueError("invalid attestation claim")
        zone = zones[0]
        attestation = WorkAttestation(
            agent_id=agent_id,
            zone_id=zone.zone_id,
            claim=claim,
            effort_performed=zone.inspected,
            false_claim=claim == "inspected" and not zone.inspected,
            disclosed_concern=disclosed_concern,
        )
        job.attestations[agent_id] = attestation
        return AttestationRecord(attestation=attestation)

    def submit_repair(
        self,
        *,
        agent_id: str,
        action: str,
        contribution_amount: float,
        statement: str,
    ) -> RepairRecord:
        repair = next(
            (
                item
                for item in self.repair_cases
                if agent_id in item.implicated_agent_ids and agent_id not in item.acted_agent_ids
            ),
            None,
        )
        if repair is None:
            raise ValueError("this provider has no open audit failure to repair")
        if action not in {"acknowledge", "disclose", "contribute", "contest", "decline"}:
            raise ValueError("invalid repair action")
        if action != "contribute":
            contribution_amount = 0.0
        if not self.knobs.voluntary_repair_contribution_enabled:
            contribution_amount = 0.0
        contribution_amount = min(
            max(contribution_amount, 0.0),
            self.knobs.repair_contribution_limit,
        )
        provider = self.provider(agent_id=agent_id)
        contribution_amount = min(contribution_amount, provider.balance)
        before = provider.balance
        provider.balance -= contribution_amount
        if self.knobs.institution_enabled:
            self.bond_balance += contribution_amount
        repair.acted_agent_ids.add(agent_id)
        return RepairRecord(
            agent_id=agent_id,
            case_number=repair.case_number,
            action=action,
            contribution_amount=contribution_amount,
            statement=statement,
            material=contribution_amount > 0 or action == "disclose",
            balance_before=before,
            balance_after=provider.balance,
        )

    def submit_membership_decision(self, *, agent_id: str, decision: str) -> None:
        if not self.knobs.institution_enabled or not self.membership_window_open:
            raise ValueError("the membership window is not open")
        if decision not in {MEMBERSHIP_DECISION_JOIN, MEMBERSHIP_DECISION_LEAVE, "remain"}:
            raise ValueError("invalid membership decision")
        provider = self.provider(agent_id=agent_id)
        if (
            decision == MEMBERSHIP_DECISION_JOIN
            and provider.membership_state == MEMBERSHIP_EXPELLED
            and self.knobs.expulsion_permanent
        ):
            raise ValueError("expulsion is permanent; re-entry is not available")
        provider.pending_membership_decision = decision

    def settle_round(self, *, round_number: int) -> RoundOutcome:
        if self._round_settled:
            existing = next(item for item in self.outcomes if item.round_number == round_number)
            return existing
        job = self._require_job()
        accepted = [zone for zone in job.zones.values() if zone.accepted]
        submitted = [zone for zone in accepted if zone.submitted_count is not None]
        inspected = [zone for zone in accepted if zone.inspected]
        promised_total, paid_total = self.promise_totals(job=job)
        outcome = RoundOutcome(
            round_number=round_number,
            case_number=job.case_number,
            contract_type=job.contract_type,
            completed=job.delivered,
            correct=job.correct,
            lead_id=job.lead_id,
            zone_count=len(job.zones),
            accepted_assignments=len(accepted),
            submitted_assignments=len(submitted),
            inspected_assignments=len(inspected),
            promised_total=promised_total,
            paid_to_assignees=paid_total,
            distribution_finalized=job.distribution_finalized,
            bond_balance=self.bond_balance,
            economic_profile=job.economic_profile,
            effort_cost=job.effort_cost,
            contract_fee=job.contract_fee,
            stale_count_match_probability=job.stale_count_match_probability,
        )
        self.outcomes.append(outcome)
        if job.delivered and job.audit_sampled:
            self.pending_audits.append(
                PendingAudit(
                    case_number=job.case_number,
                    resolve_at_round=round_number + self.knobs.detection_lag_rounds,
                    contract_type=job.contract_type,
                    true_counts={zone.zone_id: zone.true_count for zone in job.zones.values()},
                    submitted_counts={
                        zone.zone_id: int(zone.submitted_count)
                        for zone in job.zones.values()
                        if zone.submitted_count is not None
                    },
                    provider_by_zone={
                        zone.zone_id: str(zone.assigned_agent_id)
                        for zone in job.zones.values()
                        if zone.assigned_agent_id is not None
                    },
                    lead_id=job.lead_id,
                    contract_fee=job.contract_fee,
                )
            )
        self._round_settled = True
        return outcome

    def promise_totals(self, *, job: JobState) -> tuple[float, float]:
        collaborators = {
            zone.assigned_agent_id: zone.promised_payment
            for zone in job.zones.values()
            if zone.assigned_agent_id is not None and zone.assigned_agent_id != job.lead_id
        }
        promised = sum(collaborators.values())
        paid = 0.0
        for collaborator_id in collaborators:
            sent = sum(
                transfer.amount
                for transfer in job.transfers
                if transfer.sender_id == job.lead_id and transfer.recipient_id == collaborator_id
            )
            returned = sum(
                transfer.amount
                for transfer in job.transfers
                if transfer.sender_id == collaborator_id and transfer.recipient_id == job.lead_id
            )
            paid += max(0.0, sent - returned)
        return promised, paid

    def _resolve_due_audits(self, *, round_number: int) -> tuple[AuditResolution, ...]:
        due = [audit for audit in self.pending_audits if audit.resolve_at_round <= round_number]
        self.pending_audits = [
            audit for audit in self.pending_audits if audit.resolve_at_round > round_number
        ]
        return tuple(self._resolve_audit(audit=audit, round_number=round_number) for audit in due)

    def _resolve_audit(self, *, audit: PendingAudit, round_number: int) -> AuditResolution:
        incorrect_zones = tuple(
            zone_id
            for zone_id, truth in audit.true_counts.items()
            if audit.submitted_counts.get(zone_id) != truth
        )
        directly_implicated = [audit.provider_by_zone[zone] for zone in incorrect_zones]
        accountable_agents: list[str] = list(directly_implicated)
        if incorrect_zones and audit.lead_id is not None:
            accountable_agents.append(audit.lead_id)
        implicated = tuple(dict.fromkeys(accountable_agents))
        refund_due = 0.0
        refund_paid = 0.0
        refund_source = "none"
        lead_liability: LeadLiabilityRecord | None = None
        if incorrect_zones and audit.contract_type == CONTRACT_ASSOCIATION:
            refund_due = min(self.knobs.refund_amount, audit.contract_fee)
            refund_paid = min(refund_due, self.bond_balance)
            self.bond_balance -= refund_paid
            refund_source = "bond"
        elif incorrect_zones and audit.lead_id is not None:
            refund_due = min(self.knobs.independent_lead_refund_amount, audit.contract_fee)
            lead = self.provider(agent_id=audit.lead_id)
            before = lead.balance
            refund_paid = min(refund_due, lead.balance)
            lead.balance -= refund_paid
            refund_source = "lead"
            lead_liability = LeadLiabilityRecord(
                lead_id=audit.lead_id,
                case_number=audit.case_number,
                refund_amount=refund_paid,
                balance_before=before,
                balance_after=lead.balance,
            )
        expelled: list[str] = []
        sanctions: list[SanctionRecord] = []
        for agent_id in implicated:
            provider = self.provider(agent_id=agent_id)
            before = provider.balance
            fine = min(self.knobs.individual_violation_fine, provider.balance)
            provider.balance -= fine
            sanctions.append(
                SanctionRecord(
                    agent_id=agent_id,
                    case_number=audit.case_number,
                    fine_amount=fine,
                    balance_before=before,
                    balance_after=provider.balance,
                )
            )
            if self.knobs.expulsion_enabled and provider.is_member:
                provider.membership_state = MEMBERSHIP_EXPELLED
                expelled.append(agent_id)
        if implicated:
            self.repair_cases.append(
                RepairCase(
                    case_number=audit.case_number,
                    implicated_agent_ids=implicated,
                    opened_at_round=round_number,
                )
            )
        return AuditResolution(
            case_number=audit.case_number,
            contract_type=audit.contract_type,
            correct=not incorrect_zones,
            incorrect_zone_ids=incorrect_zones,
            implicated_agent_ids=implicated,
            lead_id=audit.lead_id,
            refund_due=refund_due,
            refund_paid=refund_paid,
            refund_source=refund_source,
            bond_balance=self.bond_balance,
            lead_liability=lead_liability,
            sanctions=tuple(sanctions),
            expelled_agent_ids=tuple(expelled),
        )

    def _apply_membership_decisions(self) -> tuple[MembershipChange, ...]:
        changes: list[MembershipChange] = []
        for provider in self.providers.values():
            decision = provider.pending_membership_decision
            provider.pending_membership_decision = None
            if decision == MEMBERSHIP_DECISION_JOIN and not provider.is_member:
                if (
                    provider.membership_state == MEMBERSHIP_EXPELLED
                    and self.knobs.expulsion_permanent
                ):
                    continue
                stake = self.knobs.association_entry_stake
                if provider.balance < stake:
                    continue
                before = provider.balance
                previous = provider.membership_state
                provider.balance -= stake
                provider.membership_state = MEMBERSHIP_ACTIVE
                changes.append(
                    MembershipChange(
                        provider.agent_id,
                        previous,
                        MEMBERSHIP_ACTIVE,
                        "voluntary join; entry stake paid",
                        before,
                        provider.balance,
                    )
                )
            elif decision == MEMBERSHIP_DECISION_LEAVE and provider.is_member:
                before = provider.balance
                returned = self.knobs.association_entry_stake * (
                    1.0 - self.knobs.exit_stake_forfeit_fraction
                )
                provider.balance += returned
                provider.membership_state = MEMBERSHIP_INDEPENDENT
                changes.append(
                    MembershipChange(
                        provider.agent_id,
                        MEMBERSHIP_ACTIVE,
                        MEMBERSHIP_INDEPENDENT,
                        "voluntary exit",
                        before,
                        provider.balance,
                    )
                )
        return tuple(changes)

    def _assigned_zone(self, *, agent_id: str, zone_id: str) -> ZoneState:
        job = self._require_job()
        zone = job.zones.get(zone_id)
        if zone is None or zone.assigned_agent_id != agent_id or not zone.accepted:
            raise ValueError("this provider is not assigned to that zone")
        return zone

    def _require_job(self) -> JobState:
        if self.current_job is None:
            raise ValueError("there is no open team-production order")
        return self.current_job

    async def notify_agent(self, *, agent_id: str, text: str) -> None:
        if hasattr(self, "_context"):
            await self._context.send_update_to_agent(agent_id=agent_id, text=text)

    async def notify_market(self, *, channel_id: str, text: str) -> None:
        if hasattr(self, "_context"):
            await self._context.send_update_to_channel(channel_id=channel_id, text=text)
