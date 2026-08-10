"""Design invariants for the paired variable-economy pilot."""

import json
from pathlib import Path

from glossogen.runtime.scheduled_events import InjectCase, SwapAgent
from glossogen.scenarios.bonded_team_production.events import TeamProductionPrivateChannelCreated
from glossogen.scenarios.bonded_team_production.ids import (
    MARKET_CHANNEL_ID,
    MEMBERSHIP_EXPELLED,
    SUBMIT_PLEDGE_TOOL,
)
from glossogen.scenarios.bonded_team_production.knobs import BondedTeamProductionKnobs
from glossogen.scenarios.bonded_team_production.scenario import BondedTeamProductionScenario
from glossogen.scenarios.bonded_team_production.world import BondedTeamProductionWorld

PRESET_DIR = Path("src/glossogen/scenarios/bonded_team_production")
EXP_022_CONFIG_DIR = Path(
    "docs/research/covenant-game/experiments/" "EXP-022-pledge-personal-stake-pilot/configs"
)


def load_scenario(filename: str) -> BondedTeamProductionScenario:
    payload = json.loads((PRESET_DIR / filename).read_text())
    return BondedTeamProductionScenario(knobs=BondedTeamProductionKnobs.model_validate(payload))


def test_paired_conditions_receive_identical_exogenous_cases() -> None:
    independent = load_scenario("knobs_first_experiment_independent_pilot.json")
    covenant = load_scenario("knobs_first_experiment_covenant_pilot.json")
    independent_world = independent.get_world()
    covenant_world = covenant.get_world()
    assert isinstance(independent_world, BondedTeamProductionWorld)
    assert isinstance(covenant_world, BondedTeamProductionWorld)

    assert independent_world.cases == covenant_world.cases
    assert [case.economic_profile for case in independent_world.cases] == [
        "effort_favorable",
        "marginal",
        "shirking_tempting",
    ]


def test_covenant_premium_funds_bond_without_changing_operating_fee() -> None:
    independent = load_scenario("knobs_first_experiment_independent_pilot.json")
    covenant = load_scenario("knobs_first_experiment_covenant_pilot.json")
    independent_world = independent.get_world()
    covenant_world = covenant.get_world()
    assert isinstance(independent_world, BondedTeamProductionWorld)
    assert isinstance(covenant_world, BondedTeamProductionWorld)

    for independent_case, covenant_case in zip(
        independent_world.cases, covenant_world.cases, strict=True
    ):
        assert covenant_case.association_contract_fee == (
            independent_case.independent_contract_fee + 25.0
        )
        assert covenant_case.association_contract_fee - 25.0 == (
            independent_case.independent_contract_fee
        )


def test_population_diagnostic_preserves_paired_cases_and_seed44_exposure() -> None:
    independent = load_scenario("knobs_population_test_independent_seed44.json")
    covenant = load_scenario("knobs_population_test_covenant_seed44.json")
    original = load_scenario("knobs_first_experiment_independent_seed44.json")
    independent_world = independent.get_world()
    covenant_world = covenant.get_world()
    original_world = original.get_world()
    assert isinstance(independent_world, BondedTeamProductionWorld)
    assert isinstance(covenant_world, BondedTeamProductionWorld)
    assert isinstance(original_world, BondedTeamProductionWorld)

    assert independent_world.cases == covenant_world.cases
    assert len(independent_world.providers) == 6
    assert len(covenant_world.active_member_ids()) == 6
    assert [case.audit_sampled for case in independent_world.cases] == [
        True,
        True,
        True,
        True,
        False,
        False,
        True,
        False,
        True,
    ]
    for original_case, larger_case in zip(
        original_world.cases,
        independent_world.cases,
        strict=False,
    ):
        assert original_case.zones == larger_case.zones
        assert original_case.audit_sampled == larger_case.audit_sampled
        assert original_case.attestation_queried == larger_case.attestation_queried


def test_enforcement_challenge_is_paired_and_resolves_before_postshock_rounds() -> None:
    independent = load_scenario("knobs_enforcement_challenge_independent_seed44.json")
    covenant = load_scenario("knobs_enforcement_challenge_covenant_seed44.json")
    independent_world = independent.get_world()
    covenant_world = covenant.get_world()
    assert isinstance(independent_world, BondedTeamProductionWorld)
    assert isinstance(covenant_world, BondedTeamProductionWorld)

    assert independent_world.cases == covenant_world.cases
    assert len(independent_world.providers) == 6
    assert len(covenant_world.active_member_ids()) == 6

    challenge = covenant_world.cases[2]
    assert challenge.economic_profile == "enforcement_challenge"
    assert challenge.effort_cost == 60.0
    assert challenge.stale_count_match_probability == 0.0
    assert challenge.audit_sampled is True
    assert challenge.attestation_queried is True
    assert all(zone.true_count != zone.stale_count for zone in challenge.zones)
    assert covenant_world.cases[3].case_number == 4
    assert len(covenant_world.cases[3:]) == 9


def assert_stability_pair(*, independent_filename: str, covenant_filename: str) -> None:
    independent = load_scenario(independent_filename)
    covenant = load_scenario(covenant_filename)
    independent_world = independent.get_world()
    covenant_world = covenant.get_world()
    assert isinstance(independent_world, BondedTeamProductionWorld)
    assert isinstance(covenant_world, BondedTeamProductionWorld)

    assert independent_world.cases == covenant_world.cases
    assert len(independent_world.cases) == 15
    assert all(not case.audit_sampled for case in independent_world.cases[::2])
    assert all(case.audit_sampled for case in independent_world.cases[1::2])
    assert independent_world.cases[-1].audit_sampled is False

    prompts = [
        agent.system_prompt
        for agent in covenant.get_agents(
            default_model="claude-sonnet-4-6", default_provider="anthropic"
        )
    ]
    assert all("across 15 rounds" not in prompt for prompt in prompts)
    assert all("final round is not announced to you" in prompt for prompt in prompts)


def test_stability_pilot_pairs_cases_and_hides_the_horizon() -> None:
    assert_stability_pair(
        independent_filename="knobs_stability_pilot_independent_seed45.json",
        covenant_filename="knobs_stability_pilot_covenant_seed45.json",
    )


def test_stability_replication_pairs_cases_and_hides_the_horizon() -> None:
    assert_stability_pair(
        independent_filename="knobs_stability_replication_independent_seed46.json",
        covenant_filename="knobs_stability_replication_covenant_seed46.json",
    )


def test_pledge_tool_and_prompt_are_exposed_only_in_pledge_condition() -> None:
    payload = json.loads((PRESET_DIR / "knobs_default.json").read_text())
    without_pledge = BondedTeamProductionScenario(
        knobs=BondedTeamProductionKnobs.model_validate(
            {**payload, "explicit_pledge_enabled": False}
        )
    )
    with_pledge = BondedTeamProductionScenario(
        knobs=BondedTeamProductionKnobs.model_validate({**payload, "explicit_pledge_enabled": True})
    )

    control_agent = without_pledge.get_agents(
        default_model="claude-sonnet-5",
        default_provider="anthropic",
    )[0]
    pledge_agent = with_pledge.get_agents(
        default_model="claude-sonnet-5",
        default_provider="anthropic",
    )[0]

    assert SUBMIT_PLEDGE_TOOL not in control_agent.tool_names
    assert "one-time explicit pledge" not in control_agent.system_prompt
    assert SUBMIT_PLEDGE_TOOL in pledge_agent.tool_names
    assert "one-time explicit pledge" in pledge_agent.system_prompt


def test_exp022_factorial_configs_change_only_pledge_and_stake() -> None:
    filenames = [
        "no-pledge-no-cost.json",
        "pledge-only.json",
        "cost-only.json",
        "pledge-and-cost.json",
    ]
    payloads = {
        filename: json.loads((EXP_022_CONFIG_DIR / filename).read_text()) for filename in filenames
    }
    allowed_differences = {
        "explicit_pledge_enabled",
        "initial_members_pay_entry_stake",
        "association_entry_stake",
    }
    baseline = payloads["no-pledge-no-cost.json"]
    for payload in payloads.values():
        BondedTeamProductionKnobs.model_validate(payload)
        differences = {key for key, value in payload.items() if value != baseline[key]}
        assert differences <= allowed_differences
        assert payload["seed"] == 48
        assert payload["round_count"] == 6

    assert payloads["pledge-only.json"]["explicit_pledge_enabled"] is True
    assert payloads["cost-only.json"]["initial_members_pay_entry_stake"] is True
    assert payloads["cost-only.json"]["association_entry_stake"] == 30.0
    assert payloads["pledge-and-cost.json"]["explicit_pledge_enabled"] is True
    assert payloads["pledge-and-cost.json"]["initial_members_pay_entry_stake"] is True


def test_opportunist_shock_overrides_are_paired_except_for_private_objective() -> None:
    source_payload = json.loads(
        (PRESET_DIR / "knobs_stability_replication_covenant_seed46.json").read_text()
    )
    neutral_override = json.loads(
        (PRESET_DIR / "knobs_opportunist_shock_neutral_override.json").read_text()
    )
    treatment_override = json.loads(
        (PRESET_DIR / "knobs_opportunist_shock_treatment_override.json").read_text()
    )
    neutral_payload = {**source_payload, **neutral_override, "round_count": 24}
    treatment_payload = {**source_payload, **treatment_override, "round_count": 24}
    neutral = BondedTeamProductionKnobs.model_validate(neutral_payload)
    treatment = BondedTeamProductionKnobs.model_validate(treatment_payload)

    assert neutral.audit_sample_schedule == treatment.audit_sample_schedule
    assert neutral.attestation_query_schedule == treatment.attestation_query_schedule
    assert neutral.audit_sample_schedule is not None
    assert neutral.audit_sample_schedule[-1] is False

    neutral_swap = neutral.scheduled_events[0]
    treatment_swap = treatment.scheduled_events[0]
    assert isinstance(neutral_swap, SwapAgent)
    assert isinstance(treatment_swap, SwapAgent)
    assert neutral_swap.at_round == 15
    assert treatment_swap.at_round == 15
    assert neutral_swap.agent_id == "provider_d"
    assert treatment_swap.agent_id == "provider_d"
    assert neutral_swap.system_prompt is None
    assert "private objective" in (treatment_swap.system_prompt or "")


def test_scripted_violation_targets_the_audited_round_16_lead() -> None:
    source_payload = json.loads(
        (PRESET_DIR / "knobs_stability_replication_covenant_seed46.json").read_text()
    )
    neutral_override = json.loads(
        (PRESET_DIR / "knobs_scripted_violation_neutral_override.json").read_text()
    )
    treatment_override = json.loads(
        (PRESET_DIR / "knobs_scripted_violation_treatment_override.json").read_text()
    )
    neutral = BondedTeamProductionKnobs.model_validate(
        {**source_payload, **neutral_override, "round_count": 24}
    )
    treatment = BondedTeamProductionKnobs.model_validate(
        {**source_payload, **treatment_override, "round_count": 24}
    )

    assert neutral.audit_sample_schedule == treatment.audit_sample_schedule
    assert neutral.attestation_query_schedule == treatment.attestation_query_schedule
    assert neutral.audit_sample_schedule is not None
    assert neutral.attestation_query_schedule is not None
    assert neutral.audit_sample_schedule[15] is True
    assert neutral.attestation_query_schedule[15] is True

    neutral_swap = neutral.scheduled_events[0]
    treatment_swap = treatment.scheduled_events[0]
    assert isinstance(neutral_swap, SwapAgent)
    assert isinstance(treatment_swap, SwapAgent)
    assert neutral_swap.at_round == 16
    assert treatment_swap.at_round == 16
    assert neutral_swap.agent_id == "provider_f"
    assert treatment_swap.agent_id == "provider_f"
    assert neutral_swap.system_prompt is None
    assert "CONTROLLED ONE-SHOT CHALLENGE" in (treatment_swap.system_prompt or "")


def test_confirmed_external_violation_uses_normal_refund_and_expulsion_pipeline() -> None:
    scenario = load_scenario("knobs_first_experiment_covenant_pilot.json")
    world = scenario.get_world()
    assert isinstance(world, BondedTeamProductionWorld)
    world.bond_balance = 550.0

    resolution = world.resolve_confirmed_external_violation(
        round_number=2,
        case_number=16001,
        agent_id="provider_a",
        contract_fee=155.0,
    )

    assert resolution.correct is False
    assert resolution.refund_due == 155.0
    assert resolution.refund_paid == 155.0
    assert resolution.refund_source == "bond"
    assert resolution.expelled_agent_ids == ("provider_a",)
    assert world.provider(agent_id="provider_a").membership_state == MEMBERSHIP_EXPELLED
    assert world.bond_balance == 395.0
    assert world.repair_cases[-1].implicated_agent_ids == ("provider_a",)


def test_external_violation_recovery_override_targets_round_17() -> None:
    source_payload = json.loads(
        (PRESET_DIR / "knobs_stability_replication_covenant_seed46.json").read_text()
    )
    schedule_payload = json.loads(
        (PRESET_DIR / "knobs_opportunist_shock_neutral_override.json").read_text()
    )
    intervention_payload = json.loads(
        (PRESET_DIR / "knobs_external_violation_recovery_override.json").read_text()
    )
    knobs = BondedTeamProductionKnobs.model_validate(
        {
            **source_payload,
            **schedule_payload,
            **intervention_payload,
            "round_count": 24,
        }
    )

    event = knobs.scheduled_events[0]
    assert isinstance(event, InjectCase)
    assert event.at_round == 17
    assert event.payload == {
        "kind": "confirmed_external_violation",
        "case_number": 16001,
        "agent_id": "provider_f",
        "contract_fee": 155.0,
    }


def test_population_loss_overrides_scale_the_same_round_17_shock() -> None:
    expected_agents = {
        "knobs_external_violation_two_member_override.json": [
            "provider_f",
            "provider_e",
        ],
        "knobs_external_violation_three_member_override.json": [
            "provider_f",
            "provider_e",
            "provider_d",
        ],
    }

    for filename, agent_ids in expected_agents.items():
        payload = json.loads((PRESET_DIR / filename).read_text())
        schedule_payload = json.loads(
            (PRESET_DIR / "knobs_opportunist_shock_neutral_override.json").read_text()
        )
        knobs = BondedTeamProductionKnobs.model_validate(
            {
                **json.loads(
                    (PRESET_DIR / "knobs_stability_replication_covenant_seed46.json").read_text()
                ),
                **schedule_payload,
                **payload,
                "round_count": 24,
            }
        )
        events = knobs.scheduled_events

        assert len(events) == len(agent_ids)
        assert all(isinstance(event, InjectCase) for event in events)
        injected = [event for event in events if isinstance(event, InjectCase)]
        assert [event.at_round for event in injected] == [17] * len(agent_ids)
        assert [event.payload["agent_id"] for event in injected] == agent_ids
        assert [event.payload["case_number"] for event in injected] == list(
            range(16001, 16001 + len(agent_ids))
        )
        assert all(event.payload["contract_fee"] == 155.0 for event in injected)
        assert len(knobs.audit_sample_schedule or []) == 24
        assert len(knobs.attestation_query_schedule or []) == 24


def test_population_loss_short_overrides_end_at_round_21() -> None:
    source_payload = json.loads(
        (PRESET_DIR / "knobs_stability_replication_covenant_seed46.json").read_text()
    )
    for filename in (
        "knobs_external_violation_two_member_short_override.json",
        "knobs_external_violation_three_member_short_override.json",
    ):
        override = json.loads((PRESET_DIR / filename).read_text())
        knobs = BondedTeamProductionKnobs.model_validate(
            {**source_payload, **override, "round_count": 21}
        )

        assert len(knobs.audit_sample_schedule or []) == 21
        assert len(knobs.attestation_query_schedule or []) == 21
        assert all(event.at_round == 17 for event in knobs.scheduled_events)


def test_agent_created_channel_slots_start_private_and_unallocated() -> None:
    scenario = load_scenario("knobs_first_experiment_independent_pilot.json")
    channels = scenario.get_channels()
    public = next(channel for channel in channels if channel.channel_id == MARKET_CHANNEL_ID)
    private = [channel for channel in channels if channel.channel_id != MARKET_CHANNEL_ID]

    assert len(public.member_agent_ids) == 4
    assert len(private) == 24
    assert all(channel.member_agent_ids == [] for channel in private)


def test_agent_created_private_channel_membership_survives_resume() -> None:
    scenario = load_scenario("knobs_first_experiment_independent_pilot.json")
    scenario.restore_state_from_events(
        events=[
            TeamProductionPrivateChannelCreated(
                round_number=2,
                channel_id="agent_private_1",
                creator_id="provider_a",
                member_agent_ids=["provider_a", "provider_c", "provider_d"],
                name="trusted team",
            )
        ]
    )

    channel = next(item for item in scenario.get_channels() if item.channel_id == "agent_private_1")
    assert channel.name == "trusted team"
    assert channel.member_agent_ids == ["provider_a", "provider_c", "provider_d"]
    assert (
        scenario.get_channel_display_name(channel_id="agent_private_1", agent_id="provider_c")
        == "private: trusted team"
    )
