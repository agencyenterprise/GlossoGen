"""Tests for the shared-reserve commitment state machine and treatment exposure."""

from decimal import Decimal

from glossogen.scenarios.shared_reserve_commitment.knobs import (
    SharedReserveCommitmentKnobs,
    SharedReserveCondition,
)
from glossogen.scenarios.shared_reserve_commitment.scenario import SharedReserveCommitmentScenario
from glossogen.scenarios.shared_reserve_commitment.world import SharedReserveCommitmentWorld


def build_knobs(condition: SharedReserveCondition) -> SharedReserveCommitmentKnobs:
    """Build one compact valid condition with an early deterministic claim."""
    return SharedReserveCommitmentKnobs(
        round_count=8,
        max_round_duration_seconds=60.0,
        model_overrides={},
        postmortem_duration_seconds=0.0,
        replace_agent_default_channel_visibility={},
        scheduled_events=[],
        agent_max_tokens=1024,
        round_time_budget_seconds=None,
        seed=74,
        condition=condition,
        client_payment=21,
        contribution_amount=7,
        initial_endowment=Decimal("21.0"),
        client_claim_amount=14,
        client_claim_rounds=[3],
        pledge_entry_cost=Decimal("2.1"),
        horizon_disclosed=False,
    )


def submit_pair(
    world: SharedReserveCommitmentWorld,
    round_number: int,
    provider_a_action: str,
    provider_b_action: str,
) -> None:
    """Record the two required provider actions for one active round."""
    world.begin_round(round_number=round_number)
    world.submit_decision(agent_id="provider_a", action=provider_a_action)
    world.submit_decision(agent_id="provider_b", action=provider_b_action)


def test_public_ledger_reports_both_actual_actions_after_settlement() -> None:
    """Keep past actions agent-visible after both providers decide."""
    world = SharedReserveCommitmentWorld(knobs=build_knobs(SharedReserveCondition.NO_GROUP))

    submit_pair(
        world=world,
        round_number=2,
        provider_a_action="contribute",
        provider_b_action="retain",
    )
    settlement = world.settle_round(round_number=2)
    ledger = world.ledger_text(settlement=settlement)

    assert "provider_a: contribute; contributed 7; retained 14." in ledger
    assert "provider_b: retain; contributed 0; retained 21." in ledger
    assert "Reserve now: 7." in ledger
    assert "Service active: True." in ledger


def test_one_contribution_covers_the_first_common_claim() -> None:
    """Confirm that either provider can sustain the client service temporarily."""
    world = SharedReserveCommitmentWorld(knobs=build_knobs(SharedReserveCondition.NO_GROUP))

    submit_pair(
        world=world,
        round_number=2,
        provider_a_action="contribute",
        provider_b_action="retain",
    )
    world.settle_round(round_number=2)
    submit_pair(
        world=world,
        round_number=3,
        provider_a_action="contribute",
        provider_b_action="retain",
    )
    settlement = world.settle_round(round_number=3)

    assert settlement.client_claim_due is True
    assert settlement.client_claim_paid is True
    assert settlement.reserve_after_claim == 0
    assert world.service_active() is True


def test_uncovered_claim_ends_future_shared_service() -> None:
    """Ensure mutual retention creates an observable common consequence."""
    world = SharedReserveCommitmentWorld(knobs=build_knobs(SharedReserveCondition.NO_GROUP))

    submit_pair(
        world=world,
        round_number=2,
        provider_a_action="retain",
        provider_b_action="retain",
    )
    world.settle_round(round_number=2)
    submit_pair(
        world=world,
        round_number=3,
        provider_a_action="retain",
        provider_b_action="retain",
    )
    settlement = world.settle_round(round_number=3)

    assert settlement.client_claim_due is True
    assert settlement.client_claim_paid is False
    assert world.service_active() is False


def test_missed_action_is_publicly_distinct_from_retention() -> None:
    """Keep a missed tool action from crashing or being silently scored as retention."""
    world = SharedReserveCommitmentWorld(knobs=build_knobs(SharedReserveCondition.NO_GROUP))

    world.begin_round(round_number=2)
    world.submit_decision(agent_id="provider_a", action="contribute")
    settlement = world.settle_round(round_number=2)
    ledger = world.ledger_text(settlement=settlement)

    assert settlement.missing_provider_ids == ("provider_b",)
    assert "provider_b: no_decision; contributed 0; retained 0." in ledger
    assert world.provider(agent_id="provider_b").earnings == Decimal("21.0")


def test_pledge_is_exposed_and_costly_affirmation_changes_real_balance() -> None:
    """Require the pledge treatment to be observable and financially real."""
    scenario = SharedReserveCommitmentScenario(
        knobs=build_knobs(SharedReserveCondition.COSTLY_PLEDGE)
    )
    agent = scenario.get_agents(default_model="test-model", default_provider="test-provider")[0]
    setup = scenario.get_injection(round_number=1, agent_id="provider_a") or ""
    world = SharedReserveCommitmentWorld(knobs=build_knobs(SharedReserveCondition.COSTLY_PLEDGE))

    decision = world.submit_pledge(agent_id="provider_a", decision="affirm")
    amount = world.pay_pledge_entry_cost(agent_id="provider_a")

    assert "voluntarily commit to contribute 7 units" in agent.system_prompt
    assert "submit_group_pledge" in setup
    assert decision == "affirm"
    assert amount == Decimal("2.1")
    assert world.provider(agent_id="provider_a").earnings == Decimal("18.9")


def test_baseline_omits_group_and_pledge_language() -> None:
    """Avoid inducing the absent treatment in the no-group baseline prompt."""
    scenario = SharedReserveCommitmentScenario(knobs=build_knobs(SharedReserveCondition.NO_GROUP))
    agent = scenario.get_agents(default_model="test-model", default_provider="test-provider")[0]
    prompt = "\n".join(
        [
            scenario.scenario_description(),
            agent.system_prompt,
            scenario.get_injection(round_number=2, agent_id="provider_a") or "",
        ]
    ).lower()

    assert "group registry" not in prompt
    assert "pledge" not in prompt
    assert "enrollment" not in prompt
    assert "claim" in prompt
    assert "continuity reserve" in prompt
