"""Unit tests for the repeated human-parallel trust-game state machine."""

from glossogen.scenarios.repeated_trust_game.ids import TRUSTEE_ROLE, TRUSTOR_ROLE
from glossogen.scenarios.repeated_trust_game.knobs import RepeatedTrustGameKnobs, TrustGameCondition
from glossogen.scenarios.repeated_trust_game.world import RepeatedTrustGameWorld


def build_knobs(condition: TrustGameCondition) -> RepeatedTrustGameKnobs:
    """Build a compact valid configuration for one human comparison condition."""
    forfeiture_fraction = 0.0
    if condition == TrustGameCondition.COVENANT:
        forfeiture_fraction = 0.10
    return RepeatedTrustGameKnobs(
        round_count=4,
        max_round_duration_seconds=60.0,
        model_overrides={},
        postmortem_duration_seconds=0.0,
        replace_agent_default_channel_visibility={},
        scheduled_events=[],
        agent_max_tokens=1024,
        round_time_budget_seconds=None,
        seed=61,
        condition=condition,
        trustor_endowment=10,
        fixed_partner_send=7,
        transfer_multiplier=3,
        forfeiture_fraction=forfeiture_fraction,
        horizon_disclosed=False,
    )


def test_covenant_forfeits_ten_percent_of_retained_earnings() -> None:
    """The covenant fee applies to retained earnings in both standard roles."""
    world = RepeatedTrustGameWorld(knobs=build_knobs(TrustGameCondition.COVENANT))

    world.begin_round(round_number=1)
    world.submit_pledge(agent_id="participant_a", decision="affirm")
    world.submit_pledge(agent_id="participant_b", decision="affirm")
    trust = world.record_decision(agent_id="participant_a", role=TRUSTOR_ROLE, amount=7)
    return_record = world.record_decision(
        agent_id="participant_b",
        role=TRUSTEE_ROLE,
        amount=9,
    )
    outcome = world.settle_round(round_number=1)

    assert trust.gross_earnings == 3.0
    assert trust.forfeiture_paid == 0.3
    assert trust.net_earnings == 2.7
    assert return_record.gross_earnings == 12.0
    assert return_record.forfeiture_paid == 1.2
    assert return_record.net_earnings == 10.8
    assert outcome.trust_sent == 7
    assert outcome.reciprocity_returned == 9


def test_roles_counterbalance_over_an_even_horizon() -> None:
    """The two fixed participants alternate between trust and return roles."""
    world = RepeatedTrustGameWorld(knobs=build_knobs(TrustGameCondition.NO_GROUP))

    assert world.role_for(round_number=1, agent_id="participant_a") == TRUSTOR_ROLE
    assert world.role_for(round_number=1, agent_id="participant_b") == TRUSTEE_ROLE
    assert world.role_for(round_number=2, agent_id="participant_a") == TRUSTEE_ROLE
    assert world.role_for(round_number=2, agent_id="participant_b") == TRUSTOR_ROLE


def test_covenant_requires_a_structured_pledge_before_first_decision() -> None:
    """The pledge remains a logged treatment exposure, not system-prompt text only."""
    world = RepeatedTrustGameWorld(knobs=build_knobs(TrustGameCondition.COVENANT))

    world.begin_round(round_number=1)
    try:
        world.record_decision(agent_id="participant_a", role=TRUSTOR_ROLE, amount=7)
    except ValueError as exc:
        assert str(exc) == "record a pledge decision before making a game decision"
    else:
        raise AssertionError("decision was accepted without a covenant pledge response")


def test_non_covenant_conditions_reject_the_forfeiture() -> None:
    """Only the human-study covenant condition carries the ten-percent fee."""
    payload = build_knobs(TrustGameCondition.NO_COMMITMENT_GROUP).model_dump()
    payload["forfeiture_fraction"] = 0.10

    try:
        RepeatedTrustGameKnobs.model_validate(payload)
    except ValueError as exc:
        assert "only the covenant condition may charge a forfeiture" in str(exc)
    else:
        raise AssertionError("no-commitment group accepted a covenant forfeiture")
