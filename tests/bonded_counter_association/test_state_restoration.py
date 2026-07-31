"""Tests that a rewind restores balances, membership, bond state, and audits.

Fork, resume, replace-agent, and cross-run flows all rewind to a round
boundary. If restoration dropped a pending audit, every delayed consequence the
experiment measures would silently vanish at each rewind, and a resumed run
would look better behaved than it was.
"""

from typing import Any

from glossogen.scenarios.bonded_counter_association.events import (
    BondedCounterAuditResolved,
    BondedCounterAuditScheduled,
    BondedCounterBalance,
    BondedCounterCaseStarted,
    BondedCounterJobSettled,
    BondedCounterMemberExpelled,
    BondedCounterMembershipChanged,
    BondedCounterRepairWindowOpened,
)
from glossogen.scenarios.bonded_counter_association.ids import (
    CONTRACT_ASSOCIATION,
    MEMBERSHIP_ACTIVE,
    MEMBERSHIP_EXPELLED,
    MEMBERSHIP_INDEPENDENT,
)
from glossogen.scenarios.bonded_counter_association.state_restoration import build_restored_state
from tests.bonded_counter_association.world_fixtures import build_covenant_world


def _case_started(round_number: int, balances: dict[str, float]) -> BondedCounterCaseStarted:
    """Build a case-started event carrying a provider balance snapshot."""
    return BondedCounterCaseStarted(
        round_number=round_number,
        case_number=round_number,
        true_count=100,
        stale_count=104,
        stale_count_matches_true=False,
        contract_type=CONTRACT_ASSOCIATION,
        primary_counter_id="provider_a",
        verifier_id="provider_b",
        association_members=["provider_a", "provider_b", "provider_c"],
        membership_visible=True,
        bond_balance=150.0,
        association_insolvent=False,
        attestation_queried=False,
        authority_probe_target_id=None,
        provider_balances=[
            BondedCounterBalance(agent_id=agent_id, balance_before=balance, balance_after=balance)
            for agent_id, balance in balances.items()
        ],
    )


def _settled(round_number: int, correct: bool) -> BondedCounterJobSettled:
    """Build a settlement event for a delivered guaranteed job."""
    if correct:
        signed = 100
    else:
        signed = 107
    return BondedCounterJobSettled(
        round_number=round_number,
        case_number=round_number,
        contract_type=CONTRACT_ASSOCIATION,
        completed=True,
        incomplete_reason="",
        signed_count=signed,
        true_count=100,
        count_correct=correct,
        primary_counter_id="provider_a",
        verifier_id="provider_b",
        primary_inspected=False,
        verifier_recounted=False,
        contract_fee=95.0,
        bond_contribution=15.0,
        provider_payments=[
            BondedCounterBalance(agent_id="provider_a", balance_before=300.0, balance_after=340.0),
            BondedCounterBalance(agent_id="provider_b", balance_before=300.0, balance_after=340.0),
        ],
        client_fee_paid=95.0,
        client_error_loss=0.0,
    )


def test_pending_audit_survives_a_rewind() -> None:
    """An audit scheduled before the boundary must still resolve after resume."""
    events: list[Any] = [
        _case_started(round_number=1, balances={"provider_a": 300.0, "provider_b": 300.0}),
        _settled(round_number=1, correct=False),
        BondedCounterAuditScheduled(
            round_number=1,
            case_number=1,
            resolve_at_round=3,
            contract_type=CONTRACT_ASSOCIATION,
            count_correct=False,
        ),
    ]

    snapshot = build_restored_state(events=events)

    assert len(snapshot.pending_audits) == 1
    audit = snapshot.pending_audits[0]
    assert audit.case_number == 1
    assert audit.resolve_at_round == 3
    assert not audit.count_correct
    assert audit.primary_counter_id == "provider_a"
    assert audit.verifier_id == "provider_b"


def test_resolved_audit_is_not_restored_as_pending() -> None:
    """An audit that already became public must not fire a second time."""
    events: list[Any] = [
        _case_started(round_number=1, balances={"provider_a": 300.0}),
        _settled(round_number=1, correct=False),
        BondedCounterAuditScheduled(
            round_number=1,
            case_number=1,
            resolve_at_round=2,
            contract_type=CONTRACT_ASSOCIATION,
            count_correct=False,
        ),
        BondedCounterAuditResolved(
            round_number=2,
            case_number=1,
            contract_type=CONTRACT_ASSOCIATION,
            count_correct=False,
            signed_count=107,
            true_count=100,
            primary_counter_id="provider_a",
            verifier_id="provider_b",
            primary_inspected=False,
            verifier_recounted=False,
            implicated_agent_ids=["provider_a", "provider_b"],
            refund_due=100.0,
            client_error_loss=40.0,
        ),
    ]

    snapshot = build_restored_state(events=events)

    assert snapshot.pending_audits == []


def test_balances_take_the_last_recorded_value() -> None:
    """Restored balances come from the ledger events, not re-derived arithmetic."""
    events: list[Any] = [
        _case_started(round_number=1, balances={"provider_a": 300.0, "provider_b": 300.0}),
        _settled(round_number=1, correct=True),
    ]

    snapshot = build_restored_state(events=events)

    assert snapshot.balances["provider_a"] == 340.0
    assert snapshot.balances["provider_b"] == 340.0


def test_membership_and_expulsion_state_are_restored() -> None:
    """A resumed run must not hand membership back to an expelled provider."""
    events: list[Any] = [
        _case_started(round_number=1, balances={"provider_a": 300.0}),
        BondedCounterMemberExpelled(
            round_number=2,
            agent_id="provider_a",
            case_number=1,
            permanent=False,
            reentry_allowed_at_round=6,
            reason="audited incorrect guaranteed count",
        ),
        BondedCounterMembershipChanged(
            round_number=2,
            agent_id="provider_b",
            previous_state=MEMBERSHIP_ACTIVE,
            new_state=MEMBERSHIP_INDEPENDENT,
            reason="voluntary exit",
            stake_paid=0.0,
            stake_forfeited=30.0,
            balance_before=300.0,
            balance_after=330.0,
        ),
    ]

    snapshot = build_restored_state(events=events)

    assert snapshot.membership_states["provider_a"] == MEMBERSHIP_EXPELLED
    assert snapshot.reentry_rounds["provider_a"] == 6
    assert snapshot.membership_states["provider_b"] == MEMBERSHIP_INDEPENDENT
    assert snapshot.balances["provider_b"] == 330.0


def test_unanswered_repair_window_survives_a_rewind() -> None:
    """An open repair opportunity must still be open after resume."""
    events: list[Any] = [
        _case_started(round_number=1, balances={"provider_a": 300.0}),
        _settled(round_number=1, correct=False),
        BondedCounterRepairWindowOpened(
            round_number=2,
            case_number=1,
            implicated_agent_ids=["provider_a", "provider_b"],
            contribution_allowed=True,
            contribution_limit=50.0,
        ),
    ]

    snapshot = build_restored_state(events=events)

    assert len(snapshot.repair_cases) == 1
    case = snapshot.repair_cases[0]
    assert case.implicated_agent_ids == ("provider_a", "provider_b")
    assert case.acted_agent_ids == set()


def test_world_applies_a_restored_snapshot() -> None:
    """The world adopts the restored ledger rather than the knobs' opening state."""
    world = build_covenant_world(overrides={})
    events: list[Any] = [
        _case_started(round_number=1, balances={"provider_a": 300.0, "provider_b": 300.0}),
        _settled(round_number=1, correct=False),
        BondedCounterAuditScheduled(
            round_number=1,
            case_number=1,
            resolve_at_round=3,
            contract_type=CONTRACT_ASSOCIATION,
            count_correct=False,
        ),
    ]

    world.restore_state_from_events(events=events)

    assert world.provider(agent_id="provider_a").balance == 340.0
    assert len(world.outcomes) == 1
    assert len(world.public_history) == 1

    opening = world.begin_round(round_number=3)

    assert len(opening.audit_resolutions) == 1
    assert opening.audit_resolutions[0].case_number == 1
