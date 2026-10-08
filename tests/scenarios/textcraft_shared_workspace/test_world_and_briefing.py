"""Briefings, tool sets, team budgets and knob validation, without a model."""

from collections import Counter
from typing import Any

import pytest

from glossogen.runners.communication_protocol import build_full_system_prompt
from glossogen.scenarios.textcraft_shared_workspace.recipe_dealing import deal_recipes
from glossogen.scenarios.textcraft_shared_workspace.scenario import (
    TextcraftSharedWorkspaceScenario,
)
from glossogen.scenarios.textcraft_shared_workspace.state import UNCRAFT_PREFIX
from glossogen.scenarios.textcraft_shared_workspace.world import CHANNEL, TEAM
from glossogen.testing.scenario_runtime import build_scenario

pytestmark = pytest.mark.xdist_group("textcraft_shared_workspace")


def build(preset_name: str, overrides: dict[str, Any]) -> TextcraftSharedWorkspaceScenario:
    """Build from a shipped preset through the registry."""
    scenario = build_scenario(
        scenario_name="textcraft_shared_workspace",
        preset_name=preset_name,
        overrides=overrides,
    )
    assert isinstance(scenario, TextcraftSharedWorkspaceScenario)
    return scenario


def started(preset_name: str, overrides: dict[str, Any]) -> TextcraftSharedWorkspaceScenario:
    """A scenario whose first task is on the depot."""
    scenario = build(preset_name=preset_name, overrides=overrides)
    scenario.world.start(task=scenario._tasks[0])  # pyright: ignore[reportPrivateUsage]
    return scenario


def full_prompt(scenario: TextcraftSharedWorkspaceScenario) -> str:
    agent = scenario.get_agents(default_model="test", default_provider="self-hosted")[0]
    prompts = scenario.runner_prompts(agent_id=agent.agent_id)
    assert prompts is not None
    return build_full_system_prompt(base_prompt=agent.system_prompt, prompts=prompts)


def test_every_agent_gets_the_same_unassigned_briefing() -> None:
    scenario = build(preset_name="knobs_default", overrides={})
    briefings = {
        scenario.get_injection(round_number=1, agent_id=agent)
        for agent in ("crafter_1", "crafter_2", "crafter_3")
    }
    assert len(briefings) == 1
    briefing = briefings.pop()
    task = scenario._tasks[0]  # pyright: ignore[reportPrivateUsage]
    assert all(card.target in briefing for card in task.cards.values())
    assert all(recipe.command in briefing for recipe in task.recipes)
    assert "No target or recipe is\nassigned to anyone." in briefing


def test_the_team_shares_one_action_pool_sized_from_the_witness() -> None:
    scenario = started(preset_name="knobs_default", overrides={})
    world = scenario.world
    # Four columns two layers deep, five attempts per witness step.
    assert world.action_allowance == 40
    assert "40 attempts shared by the whole team" in scenario.get_injection(
        round_number=1, agent_id="crafter_2"
    )
    task = scenario._tasks[0]  # pyright: ignore[reportPrivateUsage]
    for _ in range(39):
        world.execute(agent="crafter_1", command=task.witness[-1][1], timed=False)
    assert world.actions_left() == 1
    world.execute(agent="crafter_2", command=task.witness[-1][1], timed=False)
    assert world.terminal_trigger == "actions_exhausted"
    assert world.execute(agent="crafter_3", command=task.witness[0][1], timed=False)[0] is None


def test_textcraft_pseudo_commands_are_refused_without_costing_an_action() -> None:
    scenario = started(preset_name="knobs_default", overrides={})
    for command in ("depot", "wait", "think: plan"):
        record, observation = scenario.world.execute(
            agent="crafter_1", command=command, timed=False
        )
        assert record is None
        assert "observe()" in observation
    assert scenario.world.actions_left() == scenario.world.action_allowance


def test_a_single_agent_holds_the_whole_task_and_cannot_message() -> None:
    scenario = build(preset_name="knobs_single_agent", overrides={})
    assert [role.agent_id for role in scenario.get_agent_roles(knobs={"pool_agent_count": 1})] == [
        "crafter_1"
    ]
    briefing = scenario.get_injection(round_number=1, agent_id="crafter_1")
    assert "You are the only crafter." in briefing
    agent = scenario.get_agents(default_model="test", default_provider="self-hosted")[0]
    assert agent.tool_names == ["act", "observe"]
    assert "send_message" in scenario.hidden_base_tools(agent_id="crafter_1")
    with pytest.raises(ValueError, match="single agent"):
        build(preset_name="knobs_single_agent", overrides={"comms_enabled": True})


def test_messaging_agents_are_taught_to_message_and_wait_and_silent_ones_are_not() -> None:
    talking = build(preset_name="knobs_default", overrides={})
    silent = build(preset_name="knobs_no_comms", overrides={})
    for agent in talking.get_agents(default_model="test", default_provider="self-hosted"):
        assert set(agent.tool_names) == {"send_message", "act", "observe"}
    for agent in silent.get_agents(default_model="test", default_provider="self-hosted"):
        assert set(agent.tool_names) == {"act", "observe"}
    assert "send_message(" in full_prompt(scenario=talking)
    assert 'wait_for="message"' in full_prompt(scenario=talking)
    assert "send_message(" not in full_prompt(scenario=silent)
    assert 'wait_for="message"' not in full_prompt(scenario=silent)
    assert 'wait_for="next_round"' in full_prompt(scenario=silent)


def test_silent_observations_say_nothing_about_messages() -> None:
    scenario = started(preset_name="knobs_no_comms", overrides={})
    observation = scenario.world.observe(agent="crafter_1", action_result="Observation.")
    assert "MESSAGES" not in observation
    assert "Broadcast" not in observation
    assert scenario.validate_outgoing_message(agent_id="crafter_1", channel_id=CHANNEL)


@pytest.mark.parametrize("holders", [1, 2, 3])
def test_every_recipe_is_dealt_to_that_many_agents_in_even_hands(holders: int) -> None:
    scenario = build(preset_name="knobs_default", overrides={})
    task = scenario._tasks[0]  # pyright: ignore[reportPrivateUsage]
    seats = ["crafter_1", "crafter_2", "crafter_3"]
    hands = deal_recipes(task=task, seats=seats, holders=holders)
    dealt = Counter(command for hand in hands.values() for command in hand)
    assert dealt == {recipe.command: holders for recipe in task.recipes}
    sizes = [len(hand) for hand in hands.values()]
    assert max(sizes) - min(sizes) <= 1
    assert deal_recipes(task=task, seats=seats, holders=holders) == hands


def test_a_split_briefing_shows_every_target_but_only_the_agents_own_recipes() -> None:
    scenario = build(preset_name="knobs_recipe_split", overrides={})
    task = scenario._tasks[0]  # pyright: ignore[reportPrivateUsage]
    hands = deal_recipes(task=task, seats=["crafter_1", "crafter_2", "crafter_3"], holders=1)
    for agent, hand in hands.items():
        briefing = scenario.get_injection(round_number=1, agent_id=agent)
        assert all(card.target in briefing for card in task.cards.values())
        assert {r.command for r in task.recipes if r.command in briefing} == set(hand)
        assert f"YOUR RECIPES ({len(hand)} of {len(task.recipes)})" in briefing


def test_the_token_pool_allows_its_exact_limit_and_ends_the_round_past_it() -> None:
    scenario = started(preset_name="knobs_default", overrides={"team_token_limit": 100})
    scenario.world.record_model_usage(tokens=100)
    assert scenario.world.terminal_trigger is None
    scenario.world.record_model_usage(tokens=1)
    assert scenario.world.terminal_trigger == "team_tokens_exhausted"


def test_a_closed_round_is_not_charged_tokens() -> None:
    scenario = started(preset_name="knobs_default", overrides={"team_token_limit": 100})
    scenario.world.closed = True
    scenario.world.record_model_usage(tokens=1000)
    assert scenario.world.tokens_used == 0


def test_the_broadcast_budget_allows_its_exact_cap_and_gates_late_sends() -> None:
    scenario = started(preset_name="knobs_default", overrides={"round_time_budget_seconds": 10})
    world = scenario.world
    world.on_message(agent_id="crafter_1", channel_id=CHANNEL, text="x" * 10, token_count=1)
    assert not world.budget_exceeded
    world.on_message(agent_id="crafter_1", channel_id=CHANNEL, text="x", token_count=1)
    assert world.terminal_trigger == "budget_exhausted"
    assert scenario.validate_outgoing_message(agent_id="crafter_1", channel_id=CHANNEL)
    assert scenario.validate_outgoing_message(agent_id="crafter_1", channel_id="free_dm")
    unlimited = started(preset_name="knobs_default", overrides={})
    unlimited.world.on_message(
        agent_id="crafter_1", channel_id=CHANNEL, text="x" * 10000, token_count=1
    )
    assert not unlimited.world.budget_exceeded
    assert unlimited.world.characters_used(TEAM) == 10000


def test_a_solved_round_rejects_further_actions_and_freezes_its_verdict() -> None:
    scenario = started(preset_name="knobs_default", overrides={"round_count": 2})
    task = scenario._tasks[0]  # pyright: ignore[reportPrivateUsage]
    for column, command in task.witness:
        scenario.world.execute(agent="crafter_1", command=command, timed=False)
        _ = column
    assert scenario.world.terminal_trigger == "all_targets_satisfied"
    assert scenario.world.execute(agent="crafter_1", command="depot", timed=False)[0] is None
    verdict = scenario.judge_round_result(round_number=1, trigger="solved")
    assert verdict[0].success
    scenario.world.start(scenario._tasks[1])  # pyright: ignore[reportPrivateUsage]
    assert scenario.judge_round_result(round_number=1, trigger="late") == verdict


def test_only_an_uncraft_condition_describes_uncrafting() -> None:
    for enabled in (False, True):
        scenario = started(preset_name="knobs_default", overrides={"uncraft_enabled": enabled})
        act = next(tool for tool in scenario.get_mcp_tools() if tool.name == "act")
        assert ("uncraft " in full_prompt(scenario=scenario)) == enabled
        assert ("uncraft " in act.description) == enabled
        task = scenario._tasks[0]  # pyright: ignore[reportPrivateUsage]
        _, command = task.witness[0]
        scenario.world.execute(agent="crafter_1", command=command, timed=False)
        record, _ = scenario.world.execute(
            agent="crafter_1", command=UNCRAFT_PREFIX + command, timed=False
        )
        assert record is not None and record.accepted == enabled
        assert scenario.world.actions["crafter_1"] == 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"craft_duration_s": 10.0, "virtual_clock": False},
        {"recipe_holders": 4},
        {"postmortem_enabled": True},
        {"round_time_budget_seconds": 0},
    ],
)
def test_meaningless_combinations_are_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        build(preset_name="knobs_default", overrides=overrides)
