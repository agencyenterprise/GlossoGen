"""The rules a postmortem phase has to obey, per scenario.

The phase-gate tests cover when the discussion channel opens and shuts. These
cover the two rules either side of that: a debrief must not cost the round's
communication budget, and a scenario configured without a postmortem must not
build the channel at all.

When the phase ends is platform behaviour rather than scenario behaviour: the
game clock ends it on idle or on its own wall-clock limit, and that path is
driven end to end by the `timed_out_postmortem_run` fixture in
`tests/metrics/conftest.py`, whose `postmortem_ended_timeout` test asserts every
round was cut off by the clock. It is not repeated per scenario here.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from glossogen.engine.round_world import RoundWorld
from glossogen.runtime.scenario_world import ScenarioWorld
from glossogen.scenario_protocol import PrimaryChannel, SimulationScenario
from glossogen.scenario_registry import SCENARIO_REGISTRY
from glossogen.testing.scenario_runtime import build_scenario

POSTMORTEM_SCENARIOS = sorted(
    name for name, cls in SCENARIO_REGISTRY.items() if cls.postmortem_channel_ids
)


def character_counter_of(world: ScenarioWorld, primary: PrimaryChannel) -> Callable[[], int] | None:
    """Return a reader for the characters spent on ``primary``, or None.

    Every world meters through ``RoundWorld``, so the count comes off
    ``characters_used`` for the team that owns the primary channel. A scenario
    whose primary channel no team meters, or that meters nothing at all,
    returns None and applies a different pressure axis entirely.
    """
    if not isinstance(world, RoundWorld):
        return None
    owner = world.team_for_task_channel(channel_id=primary.channel_id)
    if owner is None:
        return None
    metered = owner
    return lambda: world.characters_used(team_id=metered)


def budget_flag_of(world: ScenarioWorld) -> Callable[[], bool] | None:
    """Return a reader for "this round blew its budget", or None.

    The fallback for worlds that keep the running character count private but
    publish the verdict it produces.
    """
    flag: Any = getattr(world, "round_budget_exceeded", None)
    if flag is None:
        return None
    if callable(flag):
        return None
    return lambda: bool(getattr(world, "round_budget_exceeded"))


def publishes_a_budget_verdict(scenario_name: str) -> bool:
    """Whether this scenario's world exposes "the round overspent" as a flag.

    Worlds that meter per team answer the question per team instead, and are
    covered through their character counter by the test above.
    """
    world = build_scenario(
        scenario_name=scenario_name, preset_name="knobs_default", overrides={}
    ).get_world()
    return budget_flag_of(world=world) is not None


# Parametrized over the scenarios that publish the verdict, rather than over
# every postmortem scenario with the rest skipping: a skip reads as "did not
# run", while an absent parameter says the test never applied.
BUDGET_VERDICT_SCENARIOS = sorted(
    name for name in POSTMORTEM_SCENARIOS if publishes_a_budget_verdict(name)
)

# Switching the postmortem off is one knob everywhere except veyru, which
# rejects the combination unless its post-swap knob goes with it.
POSTMORTEM_OFF: dict[str, dict[str, Any]] = {
    "veyru": {"postmortem_enabled": False, "postmortem_after_swap": False},
}

LONG_MESSAGE = "x" * 500


def postmortem_off_for(scenario_name: str) -> dict[str, Any]:
    """Return the knob overrides that switch this scenario's postmortem off."""
    return POSTMORTEM_OFF.get(scenario_name, {"postmortem_enabled": False})


def a_member_of(scenario: SimulationScenario, channel_id: str) -> str:
    """Return an agent that belongs to ``channel_id``.

    Worlds derive the sending team from the agent, so a placeholder id is
    silently ignored and the message is never counted.
    """
    for agent in scenario.get_agents(default_model="m", default_provider="anthropic"):
        if channel_id in agent.channel_ids:
            return agent.agent_id
    raise AssertionError(f"{scenario.name()}: nobody is in {channel_id}")


def a_channel_of(scenario: SimulationScenario, channel_ids: frozenset[str]) -> str:
    """Return one of ``channel_ids`` that this configuration actually built."""
    built = {channel.channel_id for channel in scenario.get_channels()}
    live = sorted(built & channel_ids)
    assert live, f"{scenario.name()} built none of {sorted(channel_ids)}"
    return live[0]


@pytest.mark.parametrize("scenario_name", POSTMORTEM_SCENARIOS)
def test_debrief_traffic_does_not_spend_the_round_budget(scenario_name: str) -> None:
    """A debrief is meant to be free; charging for it would tax reflection.

    Every metered world documents that only its primary channel counts, and
    nothing checked it. A world that counted every channel would quietly make
    long debriefs lose rounds, which reads as agents being bad at the task.
    """
    scenario = build_scenario(
        scenario_name=scenario_name,
        preset_name="knobs_default",
        overrides={"postmortem_enabled": True},
    )
    world = scenario.get_world()
    primary = scenario.get_primary_channels()
    if not primary:
        pytest.skip(f"{scenario_name} scores no primary channel in this configuration")
    read_spend = character_counter_of(world=world, primary=primary[0])
    if read_spend is None:
        pytest.skip(f"{scenario_name} meters no per-round character budget")
    postmortem_id = a_channel_of(
        scenario=scenario, channel_ids=type(scenario).postmortem_channel_ids
    )
    primary_id = primary[0].channel_id
    debriefer = a_member_of(scenario=scenario, channel_id=postmortem_id)
    talker = a_member_of(scenario=scenario, channel_id=primary_id)
    spent_before = read_spend()

    world.on_message(agent_id=debriefer, channel_id=postmortem_id, text=LONG_MESSAGE, token_count=1)
    spent_after_debrief = read_spend()
    world.on_message(agent_id=talker, channel_id=primary_id, text=LONG_MESSAGE, token_count=1)
    spent_after_task = read_spend()

    assert (
        spent_after_debrief == spent_before
    ), f"{len(LONG_MESSAGE)} characters of debrief were charged to the round budget"
    assert spent_after_task == spent_before + len(
        LONG_MESSAGE
    ), "the same message on the task channel was not charged, so the counter proves nothing"


@pytest.mark.parametrize("scenario_name", POSTMORTEM_SCENARIOS)
def test_no_postmortem_channel_exists_when_it_is_switched_off(scenario_name: str) -> None:
    """Configured off means the channel is never built, not merely shut.

    This is what makes a send impossible rather than refused: there is no
    channel to address and no agent is a member of one.
    """
    scenario = build_scenario(
        scenario_name=scenario_name,
        preset_name="knobs_default",
        overrides=postmortem_off_for(scenario_name=scenario_name),
    )
    declared = type(scenario).postmortem_channel_ids

    built = {channel.channel_id for channel in scenario.get_channels()}
    assert not (
        built & declared
    ), f"built postmortem channels while off: {sorted(built & declared)}"

    for agent in scenario.get_agents(default_model="m", default_provider="anthropic"):
        leaked = set(agent.channel_ids) & declared
        assert not leaked, f"{agent.agent_id} still lists {sorted(leaked)} with postmortem off"


@pytest.mark.parametrize("scenario_name", POSTMORTEM_SCENARIOS)
def test_the_world_disables_nothing_when_there_is_no_postmortem(scenario_name: str) -> None:
    """A run configured without a postmortem has nothing for a swap to hide.

    The in-run swap logic forces channels in this set to invisible for the
    incoming agent. Naming a channel that was never built would hide history
    on a channel nobody has, which is silent rather than loud.
    """
    scenario = build_scenario(
        scenario_name=scenario_name,
        preset_name="knobs_default",
        overrides=postmortem_off_for(scenario_name=scenario_name),
    )
    world = scenario.get_world()

    world.disable_postmortem_globally()

    built = {channel.channel_id for channel in scenario.get_channels()}
    assert not (world.get_globally_disabled_channels() - type(scenario).postmortem_channel_ids)
    assert not (
        world.get_globally_disabled_channels() & built
    ), "disabled a channel this configuration actually built"


@pytest.mark.parametrize("scenario_name", POSTMORTEM_SCENARIOS)
def test_the_preset_and_the_declaration_agree_about_having_a_postmortem(
    scenario_name: str,
) -> None:
    """A scenario that declares postmortem channels should ship one enabled.

    Declaring the channels and shipping a preset with the phase off would mean
    the default run silently loses a feature the scenario documents.
    """
    preset = json.loads(
        (Path("src/glossogen/scenarios") / scenario_name / "knobs_default.json").read_text()
    )

    assert (
        preset.get("postmortem_enabled") is True
    ), f"{scenario_name} declares postmortem channels but its default preset disables the phase"


@pytest.mark.parametrize("scenario_name", BUDGET_VERDICT_SCENARIOS)
def test_debrief_traffic_cannot_blow_the_budget(scenario_name: str) -> None:
    """The same rule seen through the verdict rather than the running count.

    Covers the worlds that keep the character total private but publish whether
    the round overspent, which is the value the round outcome actually reads.
    """
    scenario = build_scenario(
        scenario_name=scenario_name,
        preset_name="knobs_default",
        overrides={"postmortem_enabled": True},
    )
    world = scenario.get_world()
    read_flag = budget_flag_of(world=world)
    assert read_flag is not None, f"{scenario_name} was parametrized but publishes no verdict"
    postmortem_id = a_channel_of(
        scenario=scenario, channel_ids=type(scenario).postmortem_channel_ids
    )
    debriefer = a_member_of(scenario=scenario, channel_id=postmortem_id)
    assert read_flag() is False, "the round started already over budget"

    for _ in range(40):
        world.on_message(
            agent_id=debriefer, channel_id=postmortem_id, text=LONG_MESSAGE, token_count=1
        )

    assert read_flag() is False, "debrief traffic pushed the round over its budget"
