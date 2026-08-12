"""Tests for the pledge-breach world, calibration guard, and breach detection."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from glossogen.scenarios.pledge_breach.knobs import PledgeBreachKnobs
from glossogen.scenarios.pledge_breach.world import PledgeBreachWorld

PRESETS_DIR = Path("src/glossogen/scenarios/pledge_breach")


def build_knobs(**overrides: object) -> PledgeBreachKnobs:
    """Build knobs from the covenant preset with targeted overrides."""
    config = json.loads((PRESETS_DIR / "knobs_covenant.json").read_text())
    config.update(overrides)
    return PledgeBreachKnobs.model_validate(config)


def test_preset_arms_all_validate() -> None:
    """Every bundled arm preset satisfies the calibration guard."""
    for condition in ("no_group", "group", "pledge", "cost", "covenant"):
        config = json.loads((PRESETS_DIR / f"knobs_{condition}.json").read_text())
        knobs = PledgeBreachKnobs.model_validate(config)
        assert knobs.condition.value == condition


def test_claim_covered_by_partner_alone_is_rejected() -> None:
    """A claim the scripted partner covers on its own cannot respond to the provider."""
    with pytest.raises(ValidationError, match="scripted partner contributes on its own"):
        build_knobs(claim_amount=63)


def test_claim_beyond_joint_ceiling_is_rejected() -> None:
    """A claim neither party can reach cannot respond to the provider either."""
    with pytest.raises(ValidationError, match="both providers can accumulate"):
        build_knobs(claim_amount=155)


def test_partner_script_drives_contributions() -> None:
    """The partner contributes except on its scripted retain rounds."""
    knobs = build_knobs()
    world = PledgeBreachWorld(knobs=knobs)
    world.seed_partner_pledge()
    world.submit_pledge(decision="affirm")
    world.charge_membership_cost()

    world.begin_round(round_number=3)
    world.submit_action(action="contribute")
    settled = world.settle_round(round_number=3)
    assert settled.actions.partner_action == "contribute"
    assert settled.reserve_before_claim == 14

    world.begin_round(round_number=4)
    world.submit_action(action="contribute")
    settled = world.settle_round(round_number=4)
    assert settled.actions.partner_action == "retain"
    assert settled.reserve_before_claim == 21


def test_breach_requires_an_affirmed_pledge() -> None:
    """A scripted retention is a breach only where the partner affirmed."""
    pledged = PledgeBreachWorld(knobs=build_knobs())
    pledged.seed_partner_pledge()
    pledged.submit_pledge(decision="affirm")
    pledged.charge_membership_cost()
    pledged.begin_round(round_number=4)
    pledged.submit_action(action="contribute")
    assert pledged.settle_round(round_number=4).actions.partner_breached is True
    assert pledged.breach_count() == 1

    bare = PledgeBreachWorld(knobs=build_knobs(condition="group"))
    bare.seed_partner_pledge()
    bare.begin_round(round_number=4)
    bare.submit_action(action="contribute")
    assert bare.settle_round(round_number=4).actions.partner_breached is False
    assert bare.breach_count() == 0


def test_membership_cost_reduces_the_balance_once() -> None:
    """The membership deduction applies exactly once."""
    world = PledgeBreachWorld(knobs=build_knobs())
    world.submit_pledge(decision="affirm")
    assert world.charge_membership_cost() == Decimal("2.1")
    assert world.provider().earnings == Decimal("18.9")
    with pytest.raises(ValueError, match="already paid"):
        world.charge_membership_cost()


def test_uncovered_claim_terminates_the_service() -> None:
    """Retaining through the claim round ends the service."""
    knobs = build_knobs()
    world = PledgeBreachWorld(knobs=knobs)
    world.seed_partner_pledge()
    world.submit_pledge(decision="affirm")
    world.charge_membership_cost()
    for round_number in range(2, knobs.claim_round + 1):
        world.begin_round(round_number=round_number)
        world.submit_action(action="retain")
        settlement = world.settle_round(round_number=round_number)
    assert settlement.claim_due is True
    assert settlement.claim_paid is False
    assert world.service_active() is False


def test_minimum_contributions_cover_the_claim() -> None:
    """Contributing the calibrated minimum leaves the service alive."""
    knobs = build_knobs()
    needed = (knobs.claim_amount - knobs.contribution_amount * (
        knobs.partner_contributions_through_claim()
    )) // knobs.contribution_amount
    world = PledgeBreachWorld(knobs=knobs)
    world.seed_partner_pledge()
    world.submit_pledge(decision="affirm")
    world.charge_membership_cost()
    contributed = 0
    for round_number in range(2, knobs.claim_round + 1):
        world.begin_round(round_number=round_number)
        action = "retain"
        if contributed < needed:
            action = "contribute"
            contributed += 1
        world.submit_action(action=action)
        settlement = world.settle_round(round_number=round_number)
    assert needed == 9
    assert settlement.claim_paid is True
    assert world.service_active() is True


def test_provider_sees_partner_action_in_the_round_summary() -> None:
    """The previous-round summary names the partner's action."""
    world = PledgeBreachWorld(knobs=build_knobs())
    world.seed_partner_pledge()
    world.submit_pledge(decision="affirm")
    world.charge_membership_cost()
    world.begin_round(round_number=4)
    world.submit_action(action="contribute")
    world.settle_round(round_number=4)
    summary = world.previous_round_summary()
    assert summary is not None
    assert "Provider B retained" in summary
    assert "you contributed" in summary
    assert "breach" not in summary.lower()
