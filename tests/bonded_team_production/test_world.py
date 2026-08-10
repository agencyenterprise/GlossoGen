"""Deterministic tests for necessary collaboration and redistribution."""

import json
from pathlib import Path
from typing import Any

import pytest

from glossogen.scenarios.bonded_team_production.cases import build_cases
from glossogen.scenarios.bonded_team_production.ids import (
    COVENANT_PLEDGE_TEXT,
    MEMBERSHIP_ACTIVE,
    MEMBERSHIP_DECISION_JOIN,
    MEMBERSHIP_EXPELLED,
)
from glossogen.scenarios.bonded_team_production.knobs import BondedTeamProductionKnobs
from glossogen.scenarios.bonded_team_production.world import BondedTeamProductionWorld

PRESET_DIR = Path("src/glossogen/scenarios/bonded_team_production")


def build_world(
    preset: str = "knobs_no_covenant.json",
    overrides: dict[str, Any] | None = None,
) -> BondedTeamProductionWorld:
    payload: dict[str, Any] = json.loads((PRESET_DIR / preset).read_text())
    payload.update(overrides or {})
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


def recruit_full_team(world: BondedTeamProductionWorld) -> tuple[str, list[str]]:
    job = world.current_job
    assert job is not None and job.lead_id is not None
    lead_id = job.lead_id
    candidates = [item for item in world.eligible_provider_ids() if item != lead_id]
    open_zones = [zone.zone_id for zone in job.zones.values() if zone.assigned_agent_id is None]
    selected = candidates[: len(open_zones)]
    for zone_id, provider_id in zip(open_zones, selected, strict=True):
        world.offer_assignment(
            lead_id=lead_id,
            zone_id=zone_id,
            provider_id=provider_id,
            promised_payment=35.0,
        )
        world.respond_to_assignment(
            provider_id=provider_id,
            zone_id=zone_id,
            response="accept",
        )
    return lead_id, selected


def test_initial_members_pay_a_real_entry_stake() -> None:
    world = build_world(
        preset="knobs_default.json",
        overrides={
            "association_entry_stake": 30.0,
            "initial_members_pay_entry_stake": True,
        },
    )

    provider = world.provider(agent_id="provider_a")
    assert provider.balance == 270.0
    assert provider.membership_stake == 30.0

    world.begin_round(round_number=1)
    world.submit_membership_decision(agent_id="provider_a", decision="leave")
    world.begin_round(round_number=2)

    assert provider.balance == 285.0
    assert provider.membership_stake == 0.0


def test_explicit_pledge_records_one_private_decision() -> None:
    world = build_world(
        preset="knobs_default.json",
        overrides={"explicit_pledge_enabled": True},
    )

    pledge_text = world.submit_pledge(agent_id="provider_a", decision="affirm")

    assert pledge_text == COVENANT_PLEDGE_TEXT
    assert world.provider(agent_id="provider_a").pledge_decision == "affirm"
    with pytest.raises(ValueError, match="already submitted"):
        world.submit_pledge(agent_id="provider_a", decision="decline")


def test_explicit_pledge_is_unavailable_in_control_condition() -> None:
    world = build_world(preset="knobs_default.json")

    with pytest.raises(ValueError, match="disabled"):
        world.submit_pledge(agent_id="provider_a", decision="affirm")


def test_one_provider_cannot_cover_two_zones() -> None:
    world = build_world()
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None and job.lead_id is not None
    open_zones = [zone.zone_id for zone in job.zones.values() if zone.assigned_agent_id is None]
    candidate = next(item for item in world.eligible_provider_ids() if item != job.lead_id)
    world.offer_assignment(
        lead_id=job.lead_id,
        zone_id=open_zones[0],
        provider_id=candidate,
        promised_payment=35.0,
    )
    world.respond_to_assignment(
        provider_id=candidate,
        zone_id=open_zones[0],
        response="accept",
    )

    with pytest.raises(ValueError, match="more than one zone"):
        world.offer_assignment(
            lead_id=job.lead_id,
            zone_id=open_zones[1],
            provider_id=candidate,
            promised_payment=35.0,
        )


def test_delivery_requires_three_distinct_zone_reports() -> None:
    world = build_world()
    world.begin_round(round_number=1)
    lead_id, collaborators = recruit_full_team(world)
    job = world.current_job
    assert job is not None
    lead_zone = next(zone for zone in job.zones.values() if zone.assigned_agent_id == lead_id)
    world.submit_zone_count(
        agent_id=lead_id,
        zone_id=lead_zone.zone_id,
        count=lead_zone.stale_count,
    )
    first_zone = next(
        zone for zone in job.zones.values() if zone.assigned_agent_id == collaborators[0]
    )
    world.submit_zone_count(
        agent_id=collaborators[0],
        zone_id=first_zone.zone_id,
        count=first_zone.stale_count,
    )

    with pytest.raises(ValueError, match="all three"):
        world.deliver_order(lead_id=lead_id)


def test_free_riding_is_possible_and_recorded_without_blocking_delivery() -> None:
    world = build_world(overrides={"stale_count_match_probability": 1.0})
    world.begin_round(round_number=1)
    lead_id, _ = recruit_full_team(world)
    job = world.current_job
    assert job is not None
    for zone in job.zones.values():
        assert zone.assigned_agent_id is not None
        world.submit_zone_count(
            agent_id=zone.assigned_agent_id,
            zone_id=zone.zone_id,
            count=zone.stale_count,
        )

    delivery = world.deliver_order(lead_id=lead_id)
    world.finalize_distribution(lead_id=lead_id)
    outcome = world.settle_round(round_number=1)

    assert delivery.correct
    assert outcome.completed
    assert outcome.inspected_assignments == 0
    assert outcome.accepted_assignments == 3


def test_lead_can_underpay_an_accepted_promise_and_metric_inputs_preserve_gap() -> None:
    world = build_world(overrides={"stale_count_match_probability": 1.0})
    world.begin_round(round_number=1)
    lead_id, collaborators = recruit_full_team(world)
    job = world.current_job
    assert job is not None
    for zone in job.zones.values():
        assert zone.assigned_agent_id is not None
        world.submit_zone_count(
            agent_id=zone.assigned_agent_id,
            zone_id=zone.zone_id,
            count=zone.stale_count,
        )
    world.deliver_order(lead_id=lead_id)
    world.transfer_funds(
        sender_id=lead_id,
        recipient_id=collaborators[0],
        amount=35.0,
        note="promised zone payment",
    )
    world.transfer_funds(
        sender_id=lead_id,
        recipient_id=collaborators[1],
        amount=10.0,
        note="partial zone payment",
    )
    promised, paid = world.finalize_distribution(lead_id=lead_id)

    assert promised == 70.0
    assert paid == 45.0


def test_covenant_failure_draws_refund_from_bond_and_expels_faulty_provider() -> None:
    world = build_world(
        preset="knobs_default.json",
        overrides={
            "detection_probability": 1.0,
            "detection_lag_rounds": 1,
            "stale_count_match_probability": 0.0,
        },
    )
    world.begin_round(round_number=1)
    lead_id, _ = recruit_full_team(world)
    job = world.current_job
    assert job is not None
    faulty_id = ""
    for index, zone in enumerate(job.zones.values()):
        assert zone.assigned_agent_id is not None
        if index == 1:
            faulty_id = zone.assigned_agent_id
            submitted = zone.stale_count
        else:
            world.inspect_zone(agent_id=zone.assigned_agent_id, zone_id=zone.zone_id)
            submitted = zone.true_count
        world.submit_zone_count(
            agent_id=zone.assigned_agent_id,
            zone_id=zone.zone_id,
            count=submitted,
        )
    world.deliver_order(lead_id=lead_id)
    world.finalize_distribution(lead_id=lead_id)
    world.settle_round(round_number=1)
    bond_after_delivery = world.bond_balance

    opening = world.begin_round(round_number=2)

    assert len(opening.audit_resolutions) == 1
    resolution = opening.audit_resolutions[0]
    assert not resolution.correct
    assert faulty_id in resolution.implicated_agent_ids
    assert lead_id in resolution.implicated_agent_ids
    assert faulty_id in resolution.expelled_agent_ids
    assert lead_id in resolution.expelled_agent_ids
    assert resolution.refund_source == "bond"
    assert world.bond_balance < bond_after_delivery


def test_graded_enforcement_uses_probation_before_expulsion() -> None:
    world = build_world(
        preset="knobs_default.json",
        overrides={"expulsion_violation_threshold": 2},
    )

    first = world.resolve_confirmed_external_violation(
        round_number=2,
        case_number=16001,
        agent_id="provider_a",
        contract_fee=120.0,
    )

    provider = world.provider(agent_id="provider_a")
    assert first.probationed_agent_ids == ("provider_a",)
    assert first.expelled_agent_ids == ()
    assert first.sanctions[0].confirmed_violation_count == 1
    assert provider.confirmed_violation_count == 1
    assert provider.membership_state == MEMBERSHIP_ACTIVE

    second = world.resolve_confirmed_external_violation(
        round_number=3,
        case_number=16002,
        agent_id="provider_a",
        contract_fee=120.0,
    )

    assert second.probationed_agent_ids == ()
    assert second.expelled_agent_ids == ("provider_a",)
    assert second.sanctions[0].confirmed_violation_count == 2
    assert provider.confirmed_violation_count == 2
    assert provider.membership_state == MEMBERSHIP_EXPELLED


def test_permanent_expulsion_blocks_reentry_decision() -> None:
    world = build_world(preset="knobs_default.json", overrides={"expulsion_permanent": True})
    provider = world.provider(agent_id="provider_a")
    provider.membership_state = MEMBERSHIP_EXPELLED
    world.membership_window_open = True

    with pytest.raises(ValueError, match="expulsion is permanent"):
        world.submit_membership_decision(
            agent_id=provider.agent_id,
            decision=MEMBERSHIP_DECISION_JOIN,
        )


def test_non_permanent_expulsion_allows_reentry_at_next_round() -> None:
    world = build_world(preset="knobs_default.json", overrides={"expulsion_permanent": False})
    provider = world.provider(agent_id="provider_a")
    provider.membership_state = MEMBERSHIP_EXPELLED
    starting_balance = provider.balance
    world.membership_window_open = True
    world.submit_membership_decision(
        agent_id=provider.agent_id,
        decision=MEMBERSHIP_DECISION_JOIN,
    )

    world.begin_round(round_number=1)

    assert provider.membership_state == MEMBERSHIP_ACTIVE
    assert provider.balance == starting_balance - world.knobs.association_entry_stake


def test_independent_lead_refunds_client_and_is_accountable_for_team_failure() -> None:
    world = build_world(
        overrides={
            "detection_probability": 1.0,
            "detection_lag_rounds": 1,
            "stale_count_match_probability": 0.0,
        }
    )
    world.begin_round(round_number=1)
    lead_id, _ = recruit_full_team(world)
    job = world.current_job
    assert job is not None
    faulty_id = ""
    for index, zone in enumerate(job.zones.values()):
        assert zone.assigned_agent_id is not None
        if index == 1:
            faulty_id = zone.assigned_agent_id
            submitted = zone.stale_count
        else:
            world.inspect_zone(agent_id=zone.assigned_agent_id, zone_id=zone.zone_id)
            submitted = zone.true_count
        world.submit_zone_count(
            agent_id=zone.assigned_agent_id,
            zone_id=zone.zone_id,
            count=submitted,
        )
    world.deliver_order(lead_id=lead_id)
    world.finalize_distribution(lead_id=lead_id)
    world.settle_round(round_number=1)
    lead_balance_before_audit = world.provider(agent_id=lead_id).balance

    opening = world.begin_round(round_number=2)

    resolution = opening.audit_resolutions[0]
    assert resolution.lead_id == lead_id
    assert resolution.refund_source == "lead"
    assert resolution.refund_due == 110.0
    assert resolution.refund_paid == 110.0
    assert resolution.lead_liability is not None
    assert faulty_id in resolution.implicated_agent_ids
    assert lead_id in resolution.implicated_agent_ids
    assert world.provider(agent_id=lead_id).balance == lead_balance_before_audit - 140.0


def test_false_inspection_attestation_is_objective() -> None:
    world = build_world(
        overrides={
            "stale_count_match_probability": 1.0,
            "process_attestation_query_probability": 1.0,
        }
    )
    world.begin_round(round_number=1)
    lead_id, _ = recruit_full_team(world)
    job = world.current_job
    assert job is not None
    for zone in job.zones.values():
        assert zone.assigned_agent_id is not None
        world.submit_zone_count(
            agent_id=zone.assigned_agent_id,
            zone_id=zone.zone_id,
            count=zone.stale_count,
        )
    world.deliver_order(lead_id=lead_id)
    queried = world.request_attestations()
    record = world.submit_attestation(
        agent_id=queried[0],
        claim="inspected",
        disclosed_concern="",
    )

    assert record.attestation.false_claim
