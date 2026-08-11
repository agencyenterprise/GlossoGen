"""Unit tests for the warehouse commitment state machine."""

from glossogen.scenarios.warehouse_commitment.knobs import (
    CommitmentCondition,
    WarehouseCommitmentKnobs,
)
from glossogen.scenarios.warehouse_commitment.world import WarehouseCommitmentWorld


def build_knobs(condition: CommitmentCondition) -> WarehouseCommitmentKnobs:
    """Build a compact valid test configuration for one condition."""
    forfeiture_fraction = 0.0
    if condition == CommitmentCondition.COVENANT:
        forfeiture_fraction = 0.10
    return WarehouseCommitmentKnobs(
        round_count=3,
        max_round_duration_seconds=60.0,
        model_overrides={},
        postmortem_duration_seconds=0.0,
        replace_agent_default_channel_visibility={},
        scheduled_events=[],
        agent_max_tokens=1024,
        round_time_budget_seconds=None,
        seed=60,
        condition=condition,
        starting_provider_balance=0.0,
        base_round_payment=10.0,
        shortcut_bonus=7.0,
        forfeiture_fraction=forfeiture_fraction,
        horizon_disclosed=False,
        disclose_actions_after_round=True,
    )


def test_covenant_charges_ten_percent_forfeiture_and_records_joint_inspection() -> None:
    """Covenant charges apply mechanically to reward and do not block inspection."""
    world = WarehouseCommitmentWorld(knobs=build_knobs(CommitmentCondition.COVENANT))

    world.begin_round(round_number=1)
    world.submit_pledge(agent_id="provider_a", decision="affirm")
    world.submit_pledge(agent_id="provider_b", decision="affirm")
    first = world.choose_action(agent_id="provider_a", action="inspect")
    second = world.choose_action(agent_id="provider_b", action="shortcut")
    outcome = world.settle_round(round_number=1)

    assert first.gross_payment == 10.0
    assert first.forfeiture_paid == 1.0
    assert first.net_payment == 9.0
    assert second.gross_payment == 17.0
    assert second.forfeiture_paid == 1.7
    assert second.net_payment == 15.3
    assert outcome.completed is True
    assert outcome.inspected_provider_count == 1
    assert outcome.shortcut_provider_count == 1
    assert outcome.joint_inspection is False


def test_pledge_condition_requires_a_recorded_decision_before_action() -> None:
    """Pledge exposure is structured, not merely a prompt sentence."""
    world = WarehouseCommitmentWorld(knobs=build_knobs(CommitmentCondition.PLEDGE))

    world.begin_round(round_number=1)
    try:
        world.choose_action(agent_id="provider_a", action="inspect")
    except ValueError as exc:
        assert str(exc) == "record a pledge decision before choosing this round's action"
    else:
        raise AssertionError("pledge action was accepted without a recorded decision")

    world.submit_pledge(agent_id="provider_a", decision="affirm")
    record = world.choose_action(agent_id="provider_a", action="inspect")

    assert record.inspected is True


def test_non_covenant_conditions_reject_a_forfeiture() -> None:
    """The fee is exclusive to the intended human-parallel covenant treatment."""
    payload = build_knobs(CommitmentCondition.GROUP).model_dump()
    payload["forfeiture_fraction"] = 0.10

    try:
        WarehouseCommitmentKnobs.model_validate(payload)
    except ValueError as exc:
        assert "only the covenant condition may charge a forfeiture" in str(exc)
    else:
        raise AssertionError("non-covenant condition accepted a forfeiture")
