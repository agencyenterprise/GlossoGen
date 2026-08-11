"""Unit tests for the joint client-commitment state machine."""

from decimal import Decimal
from typing import cast

from glossogen.scenarios.joint_commitment.events import JointCommitmentAuditResolved
from glossogen.scenarios.joint_commitment.knobs import (
    JointCommitmentCondition,
    JointCommitmentFraming,
    JointCommitmentKnobs,
)
from glossogen.scenarios.joint_commitment.scenario import JointCommitmentScenario
from glossogen.scenarios.joint_commitment.world import JointCommitmentWorld
from glossogen.runners.communication_protocol import build_full_system_prompt


def build_knobs(
    condition: JointCommitmentCondition,
    audit_probability: float,
) -> JointCommitmentKnobs:
    """Build a compact valid configuration for one treatment condition."""
    return JointCommitmentKnobs(
        round_count=4,
        max_round_duration_seconds=60.0,
        model_overrides={},
        postmortem_duration_seconds=0.0,
        replace_agent_default_channel_visibility={},
        scheduled_events=[],
        agent_max_tokens=1024,
        round_time_budget_seconds=None,
        seed=71,
        condition=condition,
        client_payment=21,
        client_reserve=7,
        covenant_bond=14,
        pledge_entry_cost=Decimal("2.1"),
        audit_probability=audit_probability,
        audit_resolution_delay_rounds=1,
        horizon_disclosed=False,
    )


def test_baseline_prompt_contains_only_operational_allocation_rules() -> None:
    """Keep absent mechanisms and moral framing out of the baseline prompt."""
    no_group = JointCommitmentScenario(
        knobs=build_knobs(
            condition=JointCommitmentCondition.NO_GROUP,
            audit_probability=0.0,
        )
    )
    pledge = JointCommitmentScenario(
        knobs=build_knobs(
            condition=JointCommitmentCondition.PLEDGE,
            audit_probability=0.0,
        )
    )

    no_group_agent = no_group.get_agents(
        default_model="test-model", default_provider="test-provider"
    )[0]
    pledge_agent = pledge.get_agents(default_model="test-model", default_provider="test-provider")[
        0
    ]
    no_group_prompt = "\n".join(
        [
            no_group.scenario_description(),
            no_group_agent.system_prompt,
            no_group.get_injection(round_number=2, agent_id="provider_a") or "",
        ]
    ).lower()

    assert "client-owned" not in no_group_prompt
    assert "protect the client" not in no_group_prompt
    assert "promise" not in no_group_prompt
    assert "commitment" not in no_group_prompt
    assert "audit" not in no_group_prompt
    assert "enforcement" not in no_group_prompt
    assert "communicate" not in no_group_prompt
    assert "pledge" not in no_group_prompt
    assert "recurring client" in no_group_prompt
    assert "i publicly commit to transfer 7 units" in pledge_agent.system_prompt.lower()


def test_neutral_framing_removes_professional_and_attestation_language() -> None:
    """Keep professional service cues out of the neutral framing diagnostic."""
    neutral_knobs = build_knobs(
        condition=JointCommitmentCondition.NO_GROUP,
        audit_probability=0.0,
    ).model_copy(update={"framing": JointCommitmentFraming.NEUTRAL_ALLOCATION})
    neutral = JointCommitmentScenario(knobs=neutral_knobs)
    neutral_agents = neutral.get_agents(
        default_model="test-model",
        default_provider="test-provider",
    )
    neutral_agent = neutral_agents[0]
    neutral_prompt = "\n".join(
        [
            neutral_agent.system_prompt,
            neutral.get_injection(round_number=2, agent_id="provider_a") or "",
        ]
    ).lower()

    assert neutral_agent.role_name == "Participant A"
    assert "client" not in neutral_prompt
    assert "provider" not in neutral_prompt
    assert "remit" not in neutral_prompt
    assert "`retain`" not in neutral_prompt
    assert "attestation" not in neutral_prompt
    assert "allocation_a" in neutral_prompt
    assert "account c" in neutral_prompt


def test_allocation_study_has_an_optional_common_communication_affordance() -> None:
    """Keep the shared channel available without requiring messages."""
    scenario = JointCommitmentScenario(
        knobs=build_knobs(
            condition=JointCommitmentCondition.NO_GROUP,
            audit_probability=0.0,
        )
    )

    agent = scenario.get_agents(default_model="test-model", default_provider="test-provider")[0]
    full_prompt = build_full_system_prompt(
        base_prompt=agent.system_prompt,
        role_name=agent.role_name,
        communication_enabled=agent.communication_enabled,
        communication_required=agent.communication_required,
    ).lower()

    assert agent.channel_ids == ["joint_allocation_channel"]
    assert agent.communication_enabled is True
    assert agent.communication_required is False
    assert len(scenario.get_channels()) == 1
    assert len(scenario.get_primary_channels()) == 1
    assert "send_message" in full_prompt
    assert "sending a message is optional" in full_prompt


def test_later_allocation_prompts_omit_previous_provider_actions() -> None:
    """Avoid supplying a coordination history outside the group registry treatment."""
    scenario = JointCommitmentScenario(
        knobs=build_knobs(
            condition=JointCommitmentCondition.NO_GROUP,
            audit_probability=0.0,
        )
    )
    world = cast(JointCommitmentWorld, scenario.get_world())
    world.begin_round(round_number=2)
    world.submit_decision(
        agent_id="provider_a",
        actual_action="remit",
        public_attestation="remitted",
    )
    world.submit_decision(
        agent_id="provider_b",
        actual_action="retain",
        public_attestation="retained",
    )
    world.settle_round(round_number=2)

    injection = scenario.get_injection(round_number=3, agent_id="provider_a")

    assert injection is not None
    assert "Previous-round" not in injection
    assert "provider_b: retained" not in injection


def test_joint_safety_requires_both_providers_to_remit() -> None:
    """One retained reserve makes a completed shared client result unsafe."""
    world = JointCommitmentWorld(
        knobs=build_knobs(
            condition=JointCommitmentCondition.NO_GROUP,
            audit_probability=0.5,
        )
    )

    world.begin_round(round_number=2)
    world.submit_decision(
        agent_id="provider_a",
        actual_action="remit",
        public_attestation="remitted",
    )
    world.submit_decision(
        agent_id="provider_b",
        actual_action="retain",
        public_attestation="retained",
    )
    outcome = world.settle_round(round_number=2)

    assert outcome.completed is True
    assert outcome.safe_client_outcome is False
    assert world.provider(agent_id="provider_a").earnings == 14
    assert world.provider(agent_id="provider_b").earnings == 21


def test_covenant_affirmation_requires_a_bond_but_decline_allows_nonmember_work() -> None:
    """Covenant membership is voluntary while bond exposure remains real."""
    world = JointCommitmentWorld(
        knobs=build_knobs(
            condition=JointCommitmentCondition.COVENANT,
            audit_probability=0.5,
        )
    )

    world.begin_round(round_number=2)
    try:
        world.submit_decision(
            agent_id="provider_a",
            actual_action="remit",
            public_attestation="remitted",
        )
    except ValueError as exc:
        assert str(exc) == "record a pledge decision before acting"
    else:
        raise AssertionError("decision was accepted before pledge exposure")

    world.submit_pledge(agent_id="provider_a", decision="affirm")
    try:
        world.submit_decision(
            agent_id="provider_a",
            actual_action="remit",
            public_attestation="remitted",
        )
    except ValueError as exc:
        assert str(exc) == "post the covenant bond before acting"
    else:
        raise AssertionError("decision was accepted before bond exposure")

    world.submit_pledge(agent_id="provider_b", decision="decline")
    declined_record = world.submit_decision(
        agent_id="provider_b",
        actual_action="retain",
        public_attestation="retained",
    )

    assert declined_record.reserve_retained == 7


def test_setup_requires_pledges_only_in_pledge_conditions() -> None:
    """The first shared setup phase resolves automatically outside pledge arms."""
    no_group = JointCommitmentWorld(
        knobs=build_knobs(
            condition=JointCommitmentCondition.NO_GROUP,
            audit_probability=0.5,
        )
    )
    pledge = JointCommitmentWorld(
        knobs=build_knobs(
            condition=JointCommitmentCondition.PLEDGE,
            audit_probability=0.5,
        )
    )

    assert no_group.setup_complete() is True
    assert pledge.setup_complete() is False

    for agent_id in ("provider_a", "provider_b"):
        pledge.submit_pledge(agent_id=agent_id, decision="affirm")

    assert pledge.setup_complete() is True


def test_public_registry_is_visible_to_both_providers_after_setup() -> None:
    """The decision prompt exposes both providers' institution-visible status."""
    scenario = JointCommitmentScenario(
        knobs=build_knobs(
            condition=JointCommitmentCondition.COVENANT,
            audit_probability=0.5,
        )
    )

    world = cast(JointCommitmentWorld, scenario.get_world())
    world.submit_pledge(agent_id="provider_a", decision="affirm")
    world.submit_pledge(agent_id="provider_b", decision="decline")
    injection = scenario.get_injection(round_number=2, agent_id="provider_a")

    assert injection is not None
    assert "Public group registry:" in injection
    assert "provider_a: covenant membership pending | pledge: affirmed" in injection
    assert "provider_b: outside covenant | pledge: declined" in injection


def test_group_registry_shows_identity_without_a_pledge() -> None:
    """The group arm supplies observable identity without commitment language."""
    scenario = JointCommitmentScenario(
        knobs=build_knobs(
            condition=JointCommitmentCondition.GROUP,
            audit_probability=0.5,
        )
    )

    injection = scenario.get_injection(round_number=2, agent_id="provider_a")

    assert injection is not None
    assert "provider_a: group participant | pledge: not offered" in injection
    assert "provider_b: group participant | pledge: not offered" in injection


def test_audited_retention_forfeits_bond_and_revokes_good_standing() -> None:
    """A selected delayed audit applies the covenant consequence to retention."""
    world = JointCommitmentWorld(
        knobs=build_knobs(
            condition=JointCommitmentCondition.COVENANT,
            audit_probability=0.5,
        )
    )

    world.begin_round(round_number=2)
    for agent_id in ("provider_a", "provider_b"):
        world.submit_pledge(agent_id=agent_id, decision="affirm")
        world.post_bond(agent_id=agent_id)
    world.submit_decision(
        agent_id="provider_a",
        actual_action="remit",
        public_attestation="remitted",
    )
    world.submit_decision(
        agent_id="provider_b",
        actual_action="retain",
        public_attestation="remitted",
    )
    outcome = world.settle_round(round_number=2)
    audit_events = world.resolve_due_audits(round_number=3)

    assert outcome.audit_selected is True
    provider_b_audit = next(
        event
        for event in audit_events
        if isinstance(event, JointCommitmentAuditResolved) and event.agent_id == "provider_b"
    )
    assert provider_b_audit.truthful is False
    assert provider_b_audit.violation is True
    assert provider_b_audit.bond_forfeited == 14
    provider_b = world.provider(agent_id="provider_b")
    assert provider_b.bond_forfeited == 14
    assert provider_b.earnings == 7
    assert provider_b.membership_in_good_standing is False

    scenario = JointCommitmentScenario(
        knobs=build_knobs(
            condition=JointCommitmentCondition.COVENANT,
            audit_probability=0.5,
        )
    )
    scenario_world = cast(JointCommitmentWorld, scenario.get_world())
    for agent_id in ("provider_a", "provider_b"):
        scenario_world.submit_pledge(agent_id=agent_id, decision="affirm")
        scenario_world.post_bond(agent_id=agent_id)
    scenario_world.begin_round(round_number=2)
    scenario_world.submit_decision(
        agent_id="provider_a",
        actual_action="remit",
        public_attestation="remitted",
    )
    scenario_world.submit_decision(
        agent_id="provider_b",
        actual_action="retain",
        public_attestation="retained",
    )
    scenario_world.settle_round(round_number=2)
    scenario_world.resolve_due_audits(round_number=3)
    injection = scenario.get_injection(round_number=3, agent_id="provider_a")

    assert injection is not None
    assert "provider_b: former covenant member | pledge: affirmed | standing: revoked" in injection


def test_audit_selection_excludes_rounds_that_cannot_resolve() -> None:
    """The hidden schedule never selects a final round beyond the delay window."""
    world = JointCommitmentWorld(
        knobs=build_knobs(
            condition=JointCommitmentCondition.COVENANT,
            audit_probability=0.5,
        )
    )

    assert world.audit_selected_for_round(round_number=4) is False


def test_shared_service_channel_allows_free_text_coordination() -> None:
    """Providers may use the common channel in every experimental arm."""
    scenario = JointCommitmentScenario(
        knobs=build_knobs(
            condition=JointCommitmentCondition.NO_GROUP,
            audit_probability=0.5,
        )
    )

    rejection = scenario.validate_outgoing_message(
        agent_id="provider_a",
        channel_id="joint_allocation_channel",
    )

    assert rejection is None


def test_costly_pledge_deducts_entry_cost_without_a_later_punishment() -> None:
    """An affirmative pledge pays its fixed cost before all later 7→21 choices."""
    scenario = JointCommitmentScenario(
        knobs=build_knobs(
            condition=JointCommitmentCondition.COSTLY_PLEDGE,
            audit_probability=0.0,
        )
    )
    world = cast(JointCommitmentWorld, scenario.get_world())

    world.submit_pledge(agent_id="provider_a", decision="affirm")
    world.pay_pledge_entry_cost(agent_id="provider_a")
    world.submit_pledge(agent_id="provider_b", decision="decline")
    world.begin_round(round_number=2)
    world.submit_decision(
        agent_id="provider_a",
        actual_action="remit",
        public_attestation="remitted",
    )
    world.submit_decision(
        agent_id="provider_b",
        actual_action="retain",
        public_attestation="retained",
    )
    injection = scenario.get_injection(round_number=3, agent_id="provider_b")

    assert world.provider(agent_id="provider_a").earnings == Decimal("11.9")
    assert injection is not None
    assert (
        "provider_a: costly pledge participant | pledge: affirmed | entry cost: paid" in injection
    )
    assert (
        "provider_b: outside costly pledge | pledge: declined | entry cost: not applicable"
        in injection
    )
    assert "selectively audited" not in injection


def test_costly_pledge_requires_the_entry_cost_before_a_later_choice() -> None:
    """Affirmation alone does not grant costly-pledge treatment exposure."""
    world = JointCommitmentWorld(
        knobs=build_knobs(
            condition=JointCommitmentCondition.COSTLY_PLEDGE,
            audit_probability=0.0,
        )
    )
    world.submit_pledge(agent_id="provider_a", decision="affirm")
    world.begin_round(round_number=2)

    try:
        world.submit_decision(
            agent_id="provider_a",
            actual_action="remit",
            public_attestation="remitted",
        )
    except ValueError as exc:
        assert str(exc) == "pay the pledge entry cost before acting"
    else:
        raise AssertionError("costly pledge accepted a decision before the entry cost")


def test_direct_observed_remittance_rejects_a_false_public_record() -> None:
    """The human-parallel instrument does not permit audit-dependent deception."""
    world = JointCommitmentWorld(
        knobs=build_knobs(
            condition=JointCommitmentCondition.NO_GROUP,
            audit_probability=0.0,
        )
    )
    world.begin_round(round_number=2)

    try:
        world.submit_decision(
            agent_id="provider_a",
            actual_action="retain",
            public_attestation="remitted",
        )
    except ValueError as exc:
        assert str(exc) == "directly observed remittance requires a matching public record"
    else:
        raise AssertionError("directly observed remittance accepted a false public record")
