"""Fork/resume parity tests for the team-production economic state."""

import json
from pathlib import Path
from typing import Any

from glossogen.scenarios.bonded_team_production.cases import build_cases
from glossogen.scenarios.bonded_team_production.events import (
    TeamProductionAuditResolved,
    TeamProductionAuditScheduled,
    TeamProductionCaseStarted,
    TeamProductionFundsTransferred,
    TeamProductionLeadLiabilityCharged,
    TeamProductionMembershipDecisionSubmitted,
    TeamProductionOrderDelivered,
    TeamProductionOrderSettled,
    TeamProductionProviderSanctioned,
    TeamProductionZoneSubmitted,
    TeamZoneSnapshot,
)
from glossogen.scenarios.bonded_team_production.ids import MEMBERSHIP_ACTIVE
from glossogen.scenarios.bonded_team_production.knobs import BondedTeamProductionKnobs
from glossogen.scenarios.bonded_team_production.world import BondedTeamProductionWorld


def build_world() -> BondedTeamProductionWorld:
    payload = json.loads(
        Path("src/glossogen/scenarios/bonded_team_production/knobs_default.json").read_text()
    )
    knobs = BondedTeamProductionKnobs.model_validate(payload)
    cases = build_cases(
        seed=knobs.seed,
        round_count=knobs.round_count,
        provider_count=knobs.provider_count,
        team_size=knobs.team_size,
        true_count_min=knobs.true_count_min,
        true_count_max=knobs.true_count_max,
        stale_count_match_probability=knobs.stale_count_match_probability,
        stale_count_max_offset=knobs.stale_count_max_offset,
        detection_probability=knobs.detection_probability,
        process_attestation_query_probability=knobs.process_attestation_query_probability,
        zone_effort_cost=knobs.zone_effort_cost,
        independent_contract_fee=knobs.independent_contract_fee,
        association_contract_fee=knobs.association_contract_fee,
    )
    return BondedTeamProductionWorld(knobs=knobs, cases=cases)


def completed_round_events() -> list[Any]:
    zones = [
        TeamZoneSnapshot(zone_id="zone_1", true_count=100, stale_count=104),
        TeamZoneSnapshot(zone_id="zone_2", true_count=200, stale_count=200),
        TeamZoneSnapshot(zone_id="zone_3", true_count=300, stale_count=301),
    ]
    submissions = [
        TeamProductionZoneSubmitted(
            round_number=1,
            agent_id="provider_a",
            zone_id="zone_1",
            submitted_count=104,
            true_count=100,
            stale_count=104,
            inspected=False,
            correct=False,
        ),
        TeamProductionZoneSubmitted(
            round_number=1,
            agent_id="provider_b",
            zone_id="zone_2",
            submitted_count=200,
            true_count=200,
            stale_count=200,
            inspected=False,
            correct=True,
        ),
        TeamProductionZoneSubmitted(
            round_number=1,
            agent_id="provider_c",
            zone_id="zone_3",
            submitted_count=301,
            true_count=300,
            stale_count=301,
            inspected=False,
            correct=False,
        ),
    ]
    return [
        TeamProductionCaseStarted(
            round_number=1,
            case_number=1,
            contract_type="association",
            lead_id="provider_a",
            zones=zones,
            association_members=["provider_a", "provider_b", "provider_c"],
            bond_balance=150.0,
            audit_sampled=True,
            attestation_queried=False,
        ),
        *submissions,
        TeamProductionOrderDelivered(
            round_number=1,
            lead_id="provider_a",
            contract_type="association",
            contract_fee=180.0,
            bond_contribution=25.0,
            lead_credit=155.0,
            balance_before=300.0,
            balance_after=455.0,
            correct=False,
        ),
        TeamProductionFundsTransferred(
            round_number=1,
            sender_id="provider_a",
            recipient_id="provider_b",
            amount=35.0,
            note="zone payment",
            sender_balance_before=455.0,
            sender_balance_after=420.0,
            recipient_balance_before=300.0,
            recipient_balance_after=335.0,
        ),
        TeamProductionFundsTransferred(
            round_number=1,
            sender_id="provider_a",
            recipient_id="provider_c",
            amount=35.0,
            note="zone payment",
            sender_balance_before=420.0,
            sender_balance_after=385.0,
            recipient_balance_before=300.0,
            recipient_balance_after=335.0,
        ),
        TeamProductionMembershipDecisionSubmitted(
            round_number=1,
            agent_id="provider_d",
            decision="join",
            current_state="independent",
        ),
        TeamProductionOrderSettled(
            round_number=1,
            case_number=1,
            contract_type="association",
            completed=True,
            correct=False,
            lead_id="provider_a",
            zone_count=3,
            accepted_assignments=3,
            submitted_assignments=3,
            inspected_assignments=0,
            promised_total=70.0,
            paid_to_assignees=70.0,
            distribution_finalized=True,
            bond_balance=175.0,
        ),
        TeamProductionAuditScheduled(
            round_number=1,
            case_number=1,
            resolve_at_round=3,
            contract_type="association",
            correct=False,
        ),
    ]


def test_pending_audit_balances_bond_and_membership_decision_survive_resume() -> None:
    world = build_world()
    world.restore_state_from_events(events=completed_round_events())

    assert world.provider(agent_id="provider_a").balance == 385.0
    assert world.provider(agent_id="provider_b").balance == 335.0
    assert world.bond_balance == 175.0
    assert len(world.pending_audits) == 1
    assert world.pending_audits[0].provider_by_zone["zone_3"] == "provider_c"
    assert len(world.outcomes) == 1
    assert world.provider(agent_id="provider_d").pending_membership_decision == "join"

    world.begin_round(round_number=2)

    assert world.provider(agent_id="provider_d").membership_state == MEMBERSHIP_ACTIVE
    assert world.provider(agent_id="provider_d").balance == 240.0


def test_resolved_audit_is_not_replayed_and_sanction_state_is_preserved() -> None:
    events = [
        *completed_round_events(),
        TeamProductionAuditResolved(
            round_number=3,
            case_number=1,
            contract_type="association",
            correct=False,
            incorrect_zone_ids=["zone_1", "zone_3"],
            implicated_agent_ids=["provider_a", "provider_c"],
            refund_due=120.0,
            refund_paid=120.0,
            bond_balance=55.0,
            expelled_agent_ids=["provider_a", "provider_c"],
        ),
        TeamProductionProviderSanctioned(
            round_number=3,
            agent_id="provider_a",
            case_number=1,
            fine_amount=30.0,
            balance_before=385.0,
            balance_after=355.0,
        ),
    ]
    world = build_world()
    world.restore_state_from_events(events=events)

    assert world.pending_audits == []
    assert world.bond_balance == 55.0
    assert world.provider(agent_id="provider_a").balance == 355.0
    assert world.provider(agent_id="provider_a").confirmed_violation_count == 1
    assert world.provider(agent_id="provider_a").membership_state == "expelled"
    assert len(world.repair_cases) == 1
    assert world.repair_cases[0].implicated_agent_ids == ("provider_a", "provider_c")


def test_probation_count_survives_resume_without_expulsion() -> None:
    events = [
        *completed_round_events(),
        TeamProductionAuditResolved(
            round_number=3,
            case_number=1,
            contract_type="association",
            correct=False,
            incorrect_zone_ids=["zone_1"],
            implicated_agent_ids=["provider_a"],
            refund_due=120.0,
            refund_paid=120.0,
            bond_balance=55.0,
            probationed_agent_ids=["provider_a"],
            expelled_agent_ids=[],
        ),
        TeamProductionProviderSanctioned(
            round_number=3,
            agent_id="provider_a",
            case_number=1,
            fine_amount=30.0,
            balance_before=385.0,
            balance_after=355.0,
            confirmed_violation_count=1,
            expulsion_violation_threshold=2,
        ),
    ]
    world = build_world()
    world.restore_state_from_events(events=events)

    assert world.provider(agent_id="provider_a").confirmed_violation_count == 1
    assert world.provider(agent_id="provider_a").membership_state == MEMBERSHIP_ACTIVE


def test_independent_lead_refund_balance_survives_resume() -> None:
    events = [
        *completed_round_events(),
        TeamProductionLeadLiabilityCharged(
            round_number=3,
            lead_id="provider_a",
            case_number=1,
            refund_amount=110.0,
            balance_before=385.0,
            balance_after=275.0,
        ),
    ]
    world = build_world()
    world.restore_state_from_events(events=events)

    assert world.provider(agent_id="provider_a").balance == 275.0
