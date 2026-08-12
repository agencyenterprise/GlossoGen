"""Tests for the pledge-breach world, calibration guard, and breach detection."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from glossogen.scenarios.pledge_breach.ids import PARTNER_INCAPACITY_LABEL
from glossogen.scenarios.pledge_breach.knobs import PledgeBreachKnobs
from glossogen.scenarios.pledge_breach.state import RoundSettlement
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
    settlements: list[RoundSettlement] = []
    for round_number in range(2, knobs.claim_round + 1):
        world.begin_round(round_number=round_number)
        world.submit_action(action="retain")
        settlements.append(world.settle_round(round_number=round_number))
    assert settlements[-1].claim_due is True
    assert settlements[-1].claim_paid is False
    assert world.service_active() is False


def test_minimum_contributions_cover_the_claim() -> None:
    """Contributing the calibrated minimum leaves the service alive."""
    knobs = build_knobs()
    needed = (
        knobs.claim_amount
        - knobs.contribution_amount * (knobs.partner_contributions_through_claim())
    ) // knobs.contribution_amount
    world = PledgeBreachWorld(knobs=knobs)
    world.seed_partner_pledge()
    world.submit_pledge(decision="affirm")
    world.charge_membership_cost()
    contributed = 0
    settlements: list[RoundSettlement] = []
    for round_number in range(2, knobs.claim_round + 1):
        world.begin_round(round_number=round_number)
        action = "retain"
        if contributed < needed:
            action = "contribute"
            contributed += 1
        world.submit_action(action=action)
        settlements.append(world.settle_round(round_number=round_number))
    assert needed == 9
    assert settlements[-1].claim_paid is True
    assert world.service_active() is True


def test_no_arm_narrates_the_information_design() -> None:
    """No prompt may tell the provider what is being withheld from it.

    Wording like "not disclosed to you" or "at an unannounced round" describes
    the experiment's information design rather than the world. A provider told it
    is being kept in the dark has reason to reason about the study instead of the
    task, which is the leak that plausibly flattened EXP-037 through EXP-043.
    Absence is conveyed by absence: the claim's size, its timing, and the horizon
    are simply never stated.
    """
    from glossogen.scenarios.pledge_breach.scenario import PledgeBreachScenario

    forbidden = (
        "not disclosed",
        "undisclosed",
        "unannounced",
        "hidden",
        "in every condition",
        "condition",
        "experiment",
    )
    for preset in sorted(PRESETS_DIR.glob("knobs_*.json")):
        config = json.loads(preset.read_text())
        scenario = PledgeBreachScenario.create_from_config(config=config)
        prompt = scenario.get_agents(default_model="m", default_provider="p")[0].system_prompt
        for phrase in forbidden:
            assert phrase not in prompt, f"{preset.name} narrates the design: {phrase!r}"


def test_allocation_requires_a_recorded_pledge_where_one_is_presented() -> None:
    """A pledge arm cannot run unpledged if its setup round ends on the clock."""
    world = PledgeBreachWorld(knobs=build_knobs())
    world.seed_partner_pledge()
    world.begin_round(round_number=2)
    with pytest.raises(ValueError, match="record your pledge decision"):
        world.submit_action(action="contribute")

    bare = PledgeBreachWorld(knobs=build_knobs(condition="group"))
    bare.begin_round(round_number=2)
    bare.submit_action(action="contribute")
    assert bare.decision_recorded() is True


def test_incapacity_framing_suppresses_the_breach_but_not_the_action() -> None:
    """The control arm keeps the reserve trajectory and drops the blame."""
    chosen = PledgeBreachWorld(knobs=build_knobs())
    incapable = PledgeBreachWorld(knobs=build_knobs(partner_retention_framing="incapacity"))
    for world in (chosen, incapable):
        world.seed_partner_pledge()
        world.submit_pledge(decision="affirm")
        world.charge_membership_cost()
        world.begin_round(round_number=4)
        world.submit_action(action="contribute")
        world.settle_round(round_number=4)

    assert chosen.reserve_balance() == incapable.reserve_balance()
    assert chosen.breach_count() == 1
    assert incapable.breach_count() == 0

    chosen_summary = chosen.previous_round_summary()
    incapable_summary = incapable.previous_round_summary()
    assert chosen_summary is not None and incapable_summary is not None
    assert "Provider B retained" in chosen_summary
    assert PARTNER_INCAPACITY_LABEL in incapable_summary
    assert "retained" not in incapable_summary


def test_incapacity_framing_never_leaks_the_word_retain_for_the_partner() -> None:
    """The public record must not describe the partner as retaining."""
    world = PledgeBreachWorld(knobs=build_knobs(partner_retention_framing="incapacity"))
    world.seed_partner_pledge()
    world.submit_pledge(decision="affirm")
    world.charge_membership_cost()
    world.begin_round(round_number=4)
    world.submit_action(action="contribute")
    settlement = world.settle_round(round_number=4)
    record = world.record_text(settlement=settlement)
    assert PARTNER_INCAPACITY_LABEL in record
    partner_line = [line for line in record.splitlines() if line.startswith("Provider B")]
    assert len(partner_line) == 1
    assert "retain" not in partner_line[0]


def test_incapacity_framing_leaves_the_system_prompt_identical() -> None:
    """The control arm differs only in the per-round label, never in the prompt."""
    from glossogen.scenarios.pledge_breach.scenario import PledgeBreachScenario

    prompts: list[str] = []
    for preset in ("knobs_covenant.json", "knobs_covenant_incapacity.json"):
        config = json.loads((PRESETS_DIR / preset).read_text())
        scenario = PledgeBreachScenario.create_from_config(config=config)
        agent = scenario.get_agents(default_model="m", default_provider="p")[0]
        prompts.append(agent.system_prompt)
    assert prompts[0] == prompts[1]


EXP046_CONFIGS = Path("docs/research/covenant-game/experiments/EXP-046-commitment-reminder/configs")


def render_injection(config_path: Path, round_number: int) -> str:
    """Render one decision round's provider injection from a config file.

    The world is driven through setup and every prior round with `contribute`,
    so the rendered text is the one a compliant provider would actually see.
    """
    from glossogen.scenarios.pledge_breach.ids import PROVIDER_ID
    from glossogen.scenarios.pledge_breach.scenario import PledgeBreachScenario

    scenario = PledgeBreachScenario.create_from_config(config=json.loads(config_path.read_text()))
    world = scenario.get_world()
    assert isinstance(world, PledgeBreachWorld)
    world.seed_partner_pledge()
    world.submit_pledge(decision="affirm")
    if world.provider().membership_cost_paid == Decimal("0.0"):
        try:
            world.charge_membership_cost()
        except ValueError:
            pass
    for played in range(2, round_number):
        world.begin_round(round_number=played)
        world.submit_action(action="contribute")
        world.settle_round(round_number=played)
    world.begin_round(round_number=round_number)
    injection = scenario.get_injection(round_number=round_number, agent_id=PROVIDER_ID)
    assert injection is not None
    return injection


def test_reminder_off_renders_the_exp045_preset_unchanged() -> None:
    """The EXP-046 baseline arm must render exactly what EXP-045's did.

    EXP-046's confirmatory contrast is `pledge_reminder` against `pledge`, and the
    `pledge` arm is the same bundled config EXP-045 launched. If adding the knob
    perturbed that rendering at all — a stray newline is enough — the baseline
    would no longer be the baseline. This makes "we only changed one thing" a
    tested property rather than a claim.
    """
    scenario_preset = render_injection(
        config_path=PRESETS_DIR / "knobs_pledge.json", round_number=6
    )
    bundled = render_injection(config_path=EXP046_CONFIGS / "knobs_pledge.json", round_number=6)
    assert scenario_preset == bundled
    assert "Standing pledge record" in bundled
    assert "Your commitment reads" not in bundled


def test_reminder_adds_exactly_one_line_at_the_preregistered_position() -> None:
    """The treatment differs from its baseline by one insertion, in one place.

    The permitted insertion is the pledge's verbatim text, and its preregistered
    position is the last thing said before the allocation instruction. Anything
    else appearing, moving, or disappearing fails.
    """
    from glossogen.scenarios.pledge_breach.ids import PLEDGE_TEXT

    off = render_injection(config_path=EXP046_CONFIGS / "knobs_pledge.json", round_number=6)
    on = render_injection(config_path=EXP046_CONFIGS / "knobs_pledge_reminder.json", round_number=6)
    off_lines = off.splitlines()
    on_lines = on.splitlines()
    added = [line for line in on_lines if line not in off_lines]
    assert len(added) == 1, f"more than one line changed: {added}"
    assert PLEDGE_TEXT in added[0]
    assert [line for line in off_lines if line not in on_lines] == []
    instruction = next(
        i for i, line in enumerate(on_lines) if line.startswith("Call `submit_action`")
    )
    assert [line for line in on_lines[:instruction] if line][-1] == added[0]


def test_reminder_is_withheld_from_a_provider_that_declined() -> None:
    """A declined pledge leaves no affirmed commitment to restate."""
    world = PledgeBreachWorld(knobs=build_knobs(commitment_reminder_enabled=True))
    world.seed_partner_pledge()
    world.submit_pledge(decision="decline")
    assert world.commitment_reminder_text() is None


def test_reminder_requires_a_condition_that_presents_a_pledge() -> None:
    """The reminder cannot be enabled where no commitment is ever affirmed."""
    with pytest.raises(ValidationError, match="requires a condition that presents a pledge"):
        build_knobs(condition="cost", commitment_reminder_enabled=True)


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
