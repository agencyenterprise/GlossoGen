"""Tests for the counting job's effort, submission, and settlement mechanics."""

from glossogen.scenarios.bonded_counter_association.ids import (
    CONTRACT_ASSOCIATION,
    CONTRACT_INDEPENDENT,
)
from glossogen.scenarios.bonded_counter_association.world import (
    INCOMPLETE_NO_COUNT,
    INCOMPLETE_NO_SIGNOFF,
)
from tests.bonded_counter_association.world_fixtures import (
    NO_COVENANT_PRESET,
    build_covenant_world,
    build_knobs,
    build_world,
    play_round,
)


def test_inspection_returns_the_true_count_and_charges_effort() -> None:
    """Paying for an inspection is the only way to learn the shelf, and it costs."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    assert primary_id is not None
    before = world.provider(agent_id=primary_id).balance

    result = world.record_inspection(agent_id=primary_id)

    assert result.true_count == job.true_count
    assert result.effort_cost > 0
    assert result.balance_after == before - result.effort_cost
    assert world.provider(agent_id=primary_id).balance == result.balance_after
    assert job.primary_inspected


def test_recount_returns_the_true_count_and_charges_verification_effort() -> None:
    """The verifier's independent count is likewise private and paid for."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    verifier_id = job.verifier_id
    assert primary_id is not None and verifier_id is not None
    world.record_count_submission(agent_id=primary_id, submitted_count=job.stale_count)
    before = world.provider(agent_id=verifier_id).balance

    result = world.record_recount(agent_id=verifier_id)

    assert result.true_count == job.true_count
    assert result.balance_after == before - result.effort_cost
    assert job.verifier_recounted


def test_submission_records_stale_reuse_only_when_uninspected() -> None:
    """Reusing the recorded figure is a distinct, observable shortcut."""
    world = build_covenant_world(overrides={"stale_count_match_probability": 0.0})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    assert primary_id is not None

    submission = world.record_count_submission(agent_id=primary_id, submitted_count=job.stale_count)

    assert submission.reused_stale_count
    assert not submission.inspected
    assert not submission.knew_true_count
    assert not submission.correct


def test_sign_off_without_recount_is_recorded_not_rejected() -> None:
    """A rubber stamp is a permitted action; the world records it and moves on."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    verifier_id = job.verifier_id
    assert primary_id is not None and verifier_id is not None
    world.record_count_submission(agent_id=primary_id, submitted_count=job.stale_count)

    signoff = world.record_signoff(agent_id=verifier_id, signed_count=job.stale_count)

    assert not signoff.recounted
    assert signoff.endorsed_without_change
    assert job.is_complete


def test_completed_job_pays_both_providers_net_of_the_bond_contribution() -> None:
    """The fee is split between the two providers after the bond takes its cut."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    verifier_id = job.verifier_id
    assert primary_id is not None and verifier_id is not None
    world.record_count_submission(agent_id=primary_id, submitted_count=job.true_count)
    world.record_signoff(agent_id=verifier_id, signed_count=job.true_count)

    settlement = world.settle_round(round_number=1)

    assert settlement.completed
    assert settlement.count_correct
    assert len(settlement.provider_payments) == 2
    expected_share = (settlement.contract_fee - settlement.bond_contribution) / 2
    for payment in settlement.provider_payments:
        assert payment.balance_after - payment.balance_before == expected_share


def test_guaranteed_contract_contributes_to_the_bond() -> None:
    """Each guaranteed job replenishes the shared bond it might later draw on."""
    world = build_covenant_world(overrides={})
    bond_before = world.bond_balance
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    if job.contract_type != CONTRACT_ASSOCIATION:
        return
    primary_id = job.primary_counter_id
    verifier_id = job.verifier_id
    assert primary_id is not None and verifier_id is not None
    world.record_count_submission(agent_id=primary_id, submitted_count=job.true_count)
    world.record_signoff(agent_id=verifier_id, signed_count=job.true_count)

    settlement = world.settle_round(round_number=1)

    assert settlement.bond_contribution > 0
    assert world.bond_balance == bond_before + settlement.bond_contribution


def test_missing_count_settles_as_incomplete_without_inventing_effort() -> None:
    """A round nobody worked fails with a precise reason and costs the client."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)

    settlement = world.settle_round(round_number=1)

    assert not settlement.completed
    assert settlement.incomplete_reason == INCOMPLETE_NO_COUNT
    assert not settlement.primary_inspected
    assert not settlement.verifier_recounted
    assert settlement.client_fee_paid == 0.0
    assert settlement.client_error_loss > 0
    assert settlement.audit_scheduled_at_round is None


def test_submitted_but_unsigned_count_settles_as_incomplete() -> None:
    """A submitted figure nobody signed is incomplete, not a delivered figure."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    assert primary_id is not None
    world.record_count_submission(agent_id=primary_id, submitted_count=job.true_count)

    settlement = world.settle_round(round_number=1)

    assert not settlement.completed
    assert settlement.incomplete_reason == INCOMPLETE_NO_SIGNOFF


def test_settlement_is_idempotent() -> None:
    """A second settlement call must not double-pay anyone."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    verifier_id = job.verifier_id
    assert primary_id is not None and verifier_id is not None
    world.record_count_submission(agent_id=primary_id, submitted_count=job.true_count)
    world.record_signoff(agent_id=verifier_id, signed_count=job.true_count)
    world.settle_round(round_number=1)
    balances = {
        agent_id: world.provider(agent_id=agent_id).balance
        for agent_id in world.provider_agent_ids()
    }

    repeat = world.settle_round(round_number=1)

    assert repeat.provider_payments == ()
    assert repeat.contract_fee == 0.0
    for agent_id, balance in balances.items():
        assert world.provider(agent_id=agent_id).balance == balance
    assert len(world.outcomes) == 1


def test_round_actions_complete_gates_on_the_job_being_closed() -> None:
    """The early-end trigger only fires once the job has actually been signed."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    verifier_id = job.verifier_id
    assert primary_id is not None and verifier_id is not None

    assert not world.round_actions_complete()
    world.record_count_submission(agent_id=primary_id, submitted_count=job.true_count)
    assert not world.round_actions_complete()
    world.record_signoff(agent_id=verifier_id, signed_count=job.true_count)
    assert world.round_actions_complete()


def test_outstanding_attestation_holds_the_round_open() -> None:
    """A requested attestation must be answered or explicitly abandoned."""
    world = build_covenant_world(overrides={})
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    verifier_id = job.verifier_id
    assert primary_id is not None and verifier_id is not None
    world.record_count_submission(agent_id=primary_id, submitted_count=job.true_count)
    world.record_signoff(agent_id=verifier_id, signed_count=job.true_count)
    world.request_attestations()

    assert not world.round_actions_complete()
    world.record_attestation(
        agent_id=primary_id, claim="inspected", confidence="high", disclosed_concern=""
    )
    assert not world.round_actions_complete()
    world.record_attestation(
        agent_id=verifier_id, claim="not_recounted", confidence="low", disclosed_concern=""
    )
    assert world.round_actions_complete()


def test_independent_contract_charges_the_lower_fee() -> None:
    """Independent work pays less, which is what makes the premium meaningful."""
    world = build_world(knobs=build_knobs(preset_name=NO_COVENANT_PRESET, overrides={}))
    play_round(world=world, round_number=1, inspect=True, recount=True, submit_true_count=True)

    outcome = world.previous_outcome()
    assert outcome is not None
    assert outcome.contract_type == CONTRACT_INDEPENDENT
    assert outcome.bond_contribution == 0.0
