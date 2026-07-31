"""Tests for the two validity properties the whole design rests on.

First: the true count must never reach an agent except as the paid result of
``inspect_shelf`` or ``recount_shelf``. If it leaks into an injection, a tool
description, or a rejection string, effort becomes pointless and every effort
measure is meaningless.

Second: C1 and C2 must offer identical measurement opportunities. If the
covenant arm were asked for more attestations, given more repair affordances, or
probed on different rounds, a difference in deception or repair could be caused
by the measurement rather than by the covenant.
"""

import re

from glossogen.scenarios.bonded_counter_association.injection_rendering import (
    render_repair_injection,
    render_round_injection,
)
from glossogen.scenarios.bonded_counter_association.knobs import BondedCounterAssociationKnobs
from glossogen.scenarios.bonded_counter_association.mcp_tools import build_mcp_tools
from glossogen.scenarios.bonded_counter_association.scenario import (
    PROMPTS_DIR,
    BondedCounterAssociationScenario,
)
from glossogen.template_renderer import TemplateRenderer
from tests.bonded_counter_association.world_fixtures import (
    CALIBRATION_PRESET,
    FULL_COVENANT_PRESET,
    NO_COVENANT_PRESET,
    build_knobs,
    build_world,
)

LEAK_SENSITIVE_ROUNDS = range(1, 9)


def _renderer() -> TemplateRenderer:
    """Build a renderer over the scenario's own prompt directory."""
    return TemplateRenderer(prompts_dirs=[PROMPTS_DIR])


def _bare_integers(text: str) -> set[int]:
    """Return every integer written as a plain count, not as a money amount.

    Money is always rendered with two decimals, so a digit run followed by a
    decimal point is a price, a balance, or a fee, never a shelf figure. This
    lets the leak check assert on unit counts specifically instead of matching
    digits anywhere in the prompt.
    """
    return {int(match) for match in re.findall(r"(?<![\d.])(\d+)(?![\d.])", text)}


def test_the_only_shelf_figure_in_an_injection_is_the_recorded_one() -> None:
    """No provider's private prompt may contain the shelf's actual figure.

    Asserting on bare integers rather than on raw substrings makes this a real
    check: the only value in the shelf-count range that may appear is the
    stale figure the primary counter is legitimately given.
    """
    knobs = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    world = build_world(knobs=knobs)
    renderer = _renderer()
    checked_rounds = 0
    for round_number in LEAK_SENSITIVE_ROUNDS:
        world.begin_round(round_number=round_number)
        job = world.current_job
        assert job is not None
        if job.stale_count == job.true_count:
            world.settle_round(round_number=round_number)
            continue
        checked_rounds += 1
        for agent_id in world.provider_agent_ids():
            text = render_round_injection(
                renderer=renderer,
                world=world,
                knobs=knobs,
                round_number=round_number,
                agent_id=agent_id,
                audit_reports=[],
            )
            shelf_figures = {
                value
                for value in _bare_integers(text=text)
                if knobs.true_count_min <= value <= knobs.true_count_max
            }
            assert (
                job.true_count not in shelf_figures
            ), f"round {round_number} injection for {agent_id} leaked the true count"
            assert shelf_figures <= {job.stale_count}, (
                f"round {round_number} injection for {agent_id} exposed unexpected shelf "
                f"figures {sorted(shelf_figures)}"
            )
        world.settle_round(round_number=round_number)
    assert checked_rounds >= 4, "the leak check must actually exercise several rounds"


def test_round_injection_shows_the_stale_figure_to_the_primary_only() -> None:
    """The recorded figure is private role information, not public market data."""
    knobs = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    world = build_world(knobs=knobs)
    renderer = _renderer()
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    primary_id = job.primary_counter_id
    assert primary_id is not None

    primary_text = render_round_injection(
        renderer=renderer,
        world=world,
        knobs=knobs,
        round_number=1,
        agent_id=primary_id,
        audit_reports=[],
    )
    assert "PRIMARY COUNTER" in primary_text
    assert str(job.stale_count) in primary_text

    outsider = next(
        agent_id
        for agent_id in world.provider_agent_ids()
        if agent_id not in (job.primary_counter_id, job.verifier_id)
    )
    outsider_text = render_round_injection(
        renderer=renderer,
        world=world,
        knobs=knobs,
        round_number=1,
        agent_id=outsider,
        audit_reports=[],
    )
    assert "NO ROLE ON THIS JOB" in outsider_text


def test_no_tool_description_contains_a_count() -> None:
    """Tool schemas must not smuggle ground truth into the agent's context."""
    knobs = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    world = build_world(knobs=knobs)
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None
    tools = build_mcp_tools(world=world, knobs=knobs, get_runtime=lambda: None)

    for tool in tools:
        assert str(job.true_count) not in tool.description
        assert str(job.stale_count) not in tool.description


def test_repair_injection_does_not_disclose_the_true_count() -> None:
    """A repair prompt names the delivered figure, never the shelf's figure."""
    knobs = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    text = render_repair_injection(
        renderer=_renderer(),
        knobs=knobs,
        case_number=1,
        signed_count=107,
        job_role="primary_counter",
    )
    assert "107" in text
    assert "100" not in text


def test_system_prompt_never_states_the_true_count() -> None:
    """The system prompt is written once and cannot carry per-round ground truth."""
    knobs = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    scenario = BondedCounterAssociationScenario(knobs=knobs)
    agents = scenario.get_agents(default_model="test-model", default_provider="test")
    world = build_world(knobs=knobs)
    world.begin_round(round_number=1)
    job = world.current_job
    assert job is not None

    for agent in agents:
        assert str(job.true_count) not in agent.system_prompt


def _measurement_opportunity_fields() -> tuple[str, ...]:
    """Knobs that decide what can be measured rather than what is treated."""
    return (
        "process_attestation_query_probability",
        "authority_boundary_probe_probability",
        "repair_window_enabled",
        "voluntary_repair_contribution_enabled",
        "repair_contribution_limit",
        "repair_window_duration_seconds",
        "detection_probability",
        "detection_lag_rounds",
        "client_incorrect_count_loss",
        "individual_violation_fine",
        "count_effort_cost",
        "verification_effort_cost",
        "independent_contract_fee",
        "starting_provider_balance",
        "true_count_min",
        "true_count_max",
        "stale_count_match_probability",
        "stale_count_max_offset",
        "provider_count",
        "round_count",
        "max_round_duration_seconds",
        "seed",
        "client_reliability_window",
        "client_exploration_probability",
        "client_default_expected_error_rate",
    )


def test_control_and_treatment_have_identical_measurement_opportunities() -> None:
    """C1 and C2 differ only in the institution, never in what is observable."""
    covenant = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    control = build_knobs(preset_name=NO_COVENANT_PRESET, overrides={})
    for field in _measurement_opportunity_fields():
        assert getattr(covenant, field) == getattr(control, field), (
            f"{field} differs between C1 and C2, so a behavioural difference could "
            "be caused by the measurement rather than the covenant"
        )


def test_control_and_treatment_differ_exactly_on_the_institution() -> None:
    """The intended treatment is present, so the contrast is not empty."""
    covenant = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    control = build_knobs(preset_name=NO_COVENANT_PRESET, overrides={})
    assert covenant.institution_enabled
    assert not control.institution_enabled
    assert covenant.shared_bond_enabled
    assert not control.shared_bond_enabled
    assert covenant.expulsion_enabled
    assert not control.expulsion_enabled
    assert covenant.initial_member_ids
    assert not control.initial_member_ids
    assert covenant.association_contract_fee > covenant.independent_contract_fee


def test_both_arms_offer_the_same_channels_and_tools() -> None:
    """A provider in either arm can say and do the same things."""
    covenant = BondedCounterAssociationScenario(
        knobs=build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    )
    control = BondedCounterAssociationScenario(
        knobs=build_knobs(preset_name=NO_COVENANT_PRESET, overrides={})
    )
    assert [channel.channel_id for channel in covenant.get_channels()] == [
        channel.channel_id for channel in control.get_channels()
    ]
    assert {tool.name for tool in covenant.get_mcp_tools()} == {
        tool.name for tool in control.get_mcp_tools()
    }
    covenant_agents = covenant.get_agents(default_model="m", default_provider="p")
    control_agents = control.get_agents(default_model="m", default_provider="p")
    assert [agent.agent_id for agent in covenant_agents] == [
        agent.agent_id for agent in control_agents
    ]
    for left, right in zip(covenant_agents, control_agents, strict=True):
        assert left.tool_names == right.tool_names
        assert left.channel_ids == right.channel_ids


def test_prompts_avoid_morally_loaded_framing() -> None:
    """Neutral framing keeps the prompt from demanding socially desirable behaviour."""
    banned = ("cheat", "cheating", "honest person", "good member", "betray", "dishonest")
    knobs = build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={})
    scenario = BondedCounterAssociationScenario(knobs=knobs)
    texts = [
        agent.system_prompt
        for agent in scenario.get_agents(default_model="m", default_provider="p")
    ]
    texts.append(scenario.scenario_description())
    for text in texts:
        lowered = text.lower()
        for word in banned:
            assert word not in lowered, f"prompt uses morally loaded term '{word}'"


def test_calibration_arm_keeps_the_same_measurement_surface() -> None:
    """C0 changes the payoffs, not what can be observed."""
    calibration = build_knobs(preset_name=CALIBRATION_PRESET, overrides={})
    control = build_knobs(preset_name=NO_COVENANT_PRESET, overrides={})
    shared = (
        "process_attestation_query_probability",
        "authority_boundary_probe_probability",
        "repair_window_enabled",
        "voluntary_repair_contribution_enabled",
        "provider_count",
        "round_count",
        "seed",
        "true_count_min",
        "true_count_max",
        "stale_count_match_probability",
    )
    for field in shared:
        assert getattr(calibration, field) == getattr(control, field), field
    assert calibration.count_effort_cost > control.count_effort_cost
    assert calibration.detection_probability < control.detection_probability
    assert calibration.individual_violation_fine < control.individual_violation_fine


def test_endogenous_enforcement_is_rejected_until_implemented() -> None:
    """A follow-up condition must fail loudly rather than silently do nothing."""
    config = {
        **build_knobs(preset_name=FULL_COVENANT_PRESET, overrides={}).model_dump(),
        "endogenous_enforcement_enabled": True,
    }
    try:
        BondedCounterAssociationKnobs.model_validate(config)
    except ValueError as error:
        assert "endogenous_enforcement_enabled" in str(error)
    else:
        raise AssertionError("C8 must be rejected until it is implemented")
