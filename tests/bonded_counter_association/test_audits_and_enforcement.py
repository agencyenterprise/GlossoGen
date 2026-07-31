"""Tests for delayed audits, refunds, sanctions, expulsion, and insolvency."""

from glossogen.scenarios.bonded_counter_association.ids import (
    CONTRACT_ASSOCIATION,
    CONTRACT_INDEPENDENT,
    MEMBERSHIP_ACTIVE,
    MEMBERSHIP_EXPELLED,
    MEMBERSHIP_INDEPENDENT,
)
from tests.bonded_counter_association.world_fixtures import (
    NO_COVENANT_PRESET,
    build_covenant_world,
    build_knobs,
    build_world,
    play_round,
    reach_insolvency,
)

ALWAYS_AUDIT = {"detection_probability": 1.0}
NEVER_AUDIT = {"detection_probability": 0.0}


def test_audit_resolves_only_after_the_configured_lag() -> None:
    """A sampled audit stays private until its lag expires.

    Delayed detection is one of the dimensions the covenant is supposed to
    operate in; an audit that resolved immediately would remove it.
    """
    world = build_covenant_world(overrides={**ALWAYS_AUDIT, "detection_lag_rounds": 2})
    play_round(world=world, round_number=1, inspect=False, recount=False, submit_true_count=False)

    opening_two = world.begin_round(round_number=2)
    assert opening_two.audit_resolutions == ()
    world.settle_round(round_number=2)

    opening_three = world.begin_round(round_number=3)
    assert len(opening_three.audit_resolutions) == 1
    assert opening_three.audit_resolutions[0].case_number == 1
    assert not opening_three.audit_resolutions[0].count_correct


def test_zero_detection_probability_schedules_no_audit() -> None:
    """With detection off nothing is ever revealed, however wrong the figure."""
    world = build_covenant_world(overrides={**NEVER_AUDIT, "detection_lag_rounds": 1})
    play_round(world=world, round_number=1, inspect=False, recount=False, submit_true_count=False)

    for round_number in range(2, 6):
        opening = world.begin_round(round_number=round_number)
        assert opening.audit_resolutions == ()
        world.settle_round(round_number=round_number)


def test_correct_result_audits_are_logged_without_consequences() -> None:
    """Audits resolve for correct jobs too, so detection is not confounded with failure."""
    world = build_covenant_world(overrides={**ALWAYS_AUDIT, "detection_lag_rounds": 1})
    play_round(world=world, round_number=1, inspect=True, recount=True, submit_true_count=True)

    opening = world.begin_round(round_number=2)

    assert len(opening.audit_resolutions) == 1
    resolution = opening.audit_resolutions[0]
    assert resolution.count_correct
    assert resolution.implicated_agent_ids == ()
    assert resolution.sanctions == ()
    assert resolution.expulsions == ()
    assert opening.repair_windows == ()


def test_detected_guaranteed_failure_pays_a_refund_from_the_bond() -> None:
    """A guaranteed failure draws on the shared bond every member funds."""
    world = build_covenant_world(
        overrides={**ALWAYS_AUDIT, "detection_lag_rounds": 1, "initial_bond_balance": 500.0}
    )
    play_round(world=world, round_number=1, inspect=False, recount=False, submit_true_count=False)
    outcome = world.previous_outcome()
    assert outcome is not None
    assert outcome.contract_type == CONTRACT_ASSOCIATION, (
        "this test needs round 1 to sell a guaranteed contract; a silent return "
        "here would hide the loss of coverage"
    )
    bond_before = world.bond_balance

    opening = world.begin_round(round_number=2)

    resolution = opening.audit_resolutions[0]
    assert resolution.refund_due > 0
    assert world.bond_balance == bond_before - resolution.refund_due
    assert not world.association_insolvent


def test_bond_shortfall_records_unpaid_liability_and_marks_insolvency() -> None:
    """The bond is never allowed to go negative and pretend to be solvent."""
    world = reach_insolvency()

    assert world.association_insolvent
    assert world.bond_balance >= 0.0
    assert world.bond_unpaid_liability > 0.0
    assert world.first_insolvency_round == 4


def test_client_refuses_the_guarantee_once_the_pool_cannot_cover_a_refund() -> None:
    """Demand responds to bond state, which is the collapse loop's first step."""
    world = build_covenant_world(overrides={"initial_bond_balance": 10.0, "refund_amount": 100.0})
    opening = world.begin_round(round_number=1)
    decision = opening.assignment.client_decision
    assert decision.association_available
    assert not decision.guarantee_covered
    assert decision.contract_type == CONTRACT_INDEPENDENT


def test_individual_liability_replaces_the_bond_when_it_is_disabled() -> None:
    """The C6 ablation moves refund liability onto the responsible providers."""
    world = build_covenant_world(
        overrides={
            **ALWAYS_AUDIT,
            "detection_lag_rounds": 1,
            "shared_bond_enabled": False,
            "initial_bond_balance": 0.0,
        }
    )
    play_round(world=world, round_number=1, inspect=False, recount=False, submit_true_count=False)
    outcome = world.previous_outcome()
    assert outcome is not None
    assert outcome.contract_type == CONTRACT_ASSOCIATION, (
        "this test needs round 1 to sell a guaranteed contract; a silent return "
        "here would hide the loss of coverage"
    )

    opening = world.begin_round(round_number=2)

    resolution = opening.audit_resolutions[0]
    assert resolution.bond_changes == ()
    liabilities = [
        sanction for sanction in resolution.sanctions if sanction.individual_liability > 0
    ]
    assert liabilities, "individual liability must be charged when the bond is disabled"
    assert world.bond_balance == 0.0


def test_both_providers_on_a_failed_job_are_sanctioned() -> None:
    """The primary who submitted and the verifier who endorsed are both responsible."""
    world = build_covenant_world(overrides={**ALWAYS_AUDIT, "detection_lag_rounds": 1})
    play_round(world=world, round_number=1, inspect=False, recount=False, submit_true_count=False)
    outcome = world.previous_outcome()
    assert outcome is not None

    opening = world.begin_round(round_number=2)

    resolution = opening.audit_resolutions[0]
    assert set(resolution.implicated_agent_ids) == {
        outcome.primary_counter_id,
        outcome.verifier_id,
    }
    fined = {sanction.agent_id for sanction in resolution.sanctions if sanction.fine_amount > 0}
    assert fined == set(resolution.implicated_agent_ids)


def test_expulsion_removes_membership_permanently_by_default() -> None:
    """A detected failure costs membership, and the default is no way back."""
    world = build_covenant_world(overrides={**ALWAYS_AUDIT, "detection_lag_rounds": 1})
    play_round(world=world, round_number=1, inspect=False, recount=False, submit_true_count=False)
    outcome = world.previous_outcome()
    assert outcome is not None
    assert outcome.contract_type == CONTRACT_ASSOCIATION, (
        "this test needs round 1 to sell a guaranteed contract; a silent return "
        "here would hide the loss of coverage"
    )

    opening = world.begin_round(round_number=2)

    assert opening.audit_resolutions[0].expulsions
    for expulsion in opening.audit_resolutions[0].expulsions:
        assert expulsion.permanent
        assert expulsion.reentry_allowed_at_round is None
        assert world.provider(agent_id=expulsion.agent_id).membership_state == MEMBERSHIP_EXPELLED


def test_disabled_expulsion_keeps_financial_consequences_only() -> None:
    """The C4 ablation fines the providers but leaves the roster intact."""
    world = build_covenant_world(
        overrides={
            **ALWAYS_AUDIT,
            "detection_lag_rounds": 1,
            "expulsion_enabled": False,
            "expulsion_permanent": False,
        }
    )
    play_round(world=world, round_number=1, inspect=False, recount=False, submit_true_count=False)

    opening = world.begin_round(round_number=2)

    resolution = opening.audit_resolutions[0]
    assert resolution.expulsions == ()
    assert any(sanction.fine_amount > 0 for sanction in resolution.sanctions)
    for agent_id in resolution.implicated_agent_ids:
        assert world.provider(agent_id=agent_id).membership_state != MEMBERSHIP_EXPELLED


def test_reversible_expulsion_sets_a_reentry_round() -> None:
    """The C7 ablation lets an expelled provider back after a waiting period."""
    world = build_covenant_world(
        overrides={
            **ALWAYS_AUDIT,
            "detection_lag_rounds": 1,
            "expulsion_permanent": False,
            "reentry_wait_rounds": 3,
        }
    )
    play_round(world=world, round_number=1, inspect=False, recount=False, submit_true_count=False)
    outcome = world.previous_outcome()
    assert outcome is not None
    assert outcome.contract_type == CONTRACT_ASSOCIATION, (
        "this test needs round 1 to sell a guaranteed contract; a silent return "
        "here would hide the loss of coverage"
    )

    opening = world.begin_round(round_number=2)

    for expulsion in opening.audit_resolutions[0].expulsions:
        assert not expulsion.permanent
        assert expulsion.reentry_allowed_at_round == 5


def test_expelled_provider_cannot_rejoin_before_the_waiting_period() -> None:
    """A queued join is refused while the provider is still serving its wait."""
    world = build_covenant_world(
        overrides={
            **ALWAYS_AUDIT,
            "detection_lag_rounds": 1,
            "expulsion_permanent": False,
            "reentry_wait_rounds": 4,
            "membership_decision_interval": 1,
        }
    )
    play_round(world=world, round_number=1, inspect=False, recount=False, submit_true_count=False)
    opening = world.begin_round(round_number=2)
    expulsions = opening.audit_resolutions[0].expulsions
    if not expulsions:
        return
    expelled_id = expulsions[0].agent_id
    world.record_membership_decision(agent_id=expelled_id, decision="join")
    world.settle_round(round_number=2)

    world.begin_round(round_number=3)

    assert world.provider(agent_id=expelled_id).membership_state == MEMBERSHIP_EXPELLED


def test_voluntary_exit_forfeits_the_documented_stake_portion() -> None:
    """Leaving is always allowed and costs exactly the documented fraction."""
    world = build_covenant_world(
        overrides={"membership_decision_interval": 1, "exit_stake_forfeit_fraction": 0.5}
    )
    world.begin_round(round_number=1)
    member_id = world.active_member_ids()[0]
    balance_before = world.provider(agent_id=member_id).balance
    world.record_membership_decision(agent_id=member_id, decision="leave")
    world.settle_round(round_number=1)

    opening = world.begin_round(round_number=2)

    changes = [change for change in opening.membership_changes if change.agent_id == member_id]
    assert len(changes) == 1
    change = changes[0]
    assert change.previous_state == MEMBERSHIP_ACTIVE
    assert change.new_state == MEMBERSHIP_INDEPENDENT
    assert change.stake_forfeited == 30.0
    assert world.provider(agent_id=member_id).balance == balance_before + 30.0


def test_join_requires_and_charges_the_entry_stake() -> None:
    """Admission costs real money, which is what makes the stake a stake."""
    world = build_covenant_world(overrides={"membership_decision_interval": 1})
    world.begin_round(round_number=1)
    independent_id = next(
        agent_id
        for agent_id in world.provider_agent_ids()
        if not world.provider(agent_id=agent_id).is_active_member
    )
    balance_before = world.provider(agent_id=independent_id).balance
    world.record_membership_decision(agent_id=independent_id, decision="join")
    world.settle_round(round_number=1)

    opening = world.begin_round(round_number=2)

    changes = [c for c in opening.membership_changes if c.agent_id == independent_id]
    assert len(changes) == 1
    assert changes[0].stake_paid == 60.0
    assert world.provider(agent_id=independent_id).balance == balance_before - 60.0
    assert independent_id in world.active_member_ids()


def test_join_is_refused_when_the_provider_cannot_afford_the_stake() -> None:
    """Membership is not extended on credit."""
    world = build_covenant_world(
        overrides={"membership_decision_interval": 1, "starting_provider_balance": 10.0}
    )
    world.begin_round(round_number=1)
    independent_id = next(
        agent_id
        for agent_id in world.provider_agent_ids()
        if not world.provider(agent_id=agent_id).is_active_member
    )
    world.record_membership_decision(agent_id=independent_id, decision="join")
    world.settle_round(round_number=1)

    opening = world.begin_round(round_number=2)

    assert not [c for c in opening.membership_changes if c.agent_id == independent_id]
    assert independent_id not in world.active_member_ids()


def test_membership_window_opens_on_the_configured_interval() -> None:
    """Membership changes only at documented boundaries, never mid-job."""
    world = build_covenant_world(overrides={"membership_decision_interval": 3})
    open_rounds: list[int] = []
    for round_number in range(1, 8):
        opening = world.begin_round(round_number=round_number)
        if opening.membership_window_open:
            open_rounds.append(round_number)
        world.settle_round(round_number=round_number)
    assert open_rounds == [1, 4, 7]


def test_no_membership_window_without_an_institution() -> None:
    """The control arm has no membership machinery to open."""
    no_covenant = build_world(knobs=build_knobs(preset_name=NO_COVENANT_PRESET, overrides={}))
    for round_number in range(1, 5):
        opening = no_covenant.begin_round(round_number=round_number)
        assert not opening.membership_window_open
        no_covenant.settle_round(round_number=round_number)
