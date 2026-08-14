"""Opening the postmortem phase has to actually open the channel.

Every scenario refuses postmortem sends outside the phase and refuses primary
sends inside it, and both checks read one flag on the world that
``on_postmortem_started`` sets. Nothing else in the suite reads that flag, so a
world that forgets to record the phase leaves every scenario silently unable to
hold a debrief: the messages are refused, the channel is empty, and the run
still completes and reports numbers.

Driving this through a real simulation does not work. Agents wake each other on
every send, so a scripted agent burns its whole script during the game phase and
is idle by the time the phase opens. Measured: 0 of 90 scripted sends landed
inside the postmortem window. Calling the transition directly is both
deterministic and the thing actually worth pinning.
"""

from pathlib import Path

import pytest

from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_registry import SCENARIO_REGISTRY
from glossogen.testing.scenario_runtime import (
    build_scenario,
    fast_round_overrides,
    run_scenario,
)

POSTMORTEM_SCENARIOS = sorted(
    name for name, cls in SCENARIO_REGISTRY.items() if cls.postmortem_channel_ids
)


def a_live_postmortem_channel(scenario: SimulationScenario) -> tuple[str, str]:
    """Return a declared postmortem channel this configuration built, and a member.

    ``postmortem_channel_ids`` is a class constant covering every mode the
    scenario can run in, so a two-team preset builds the per-team channels and
    not the shared one. Picking the first id alphabetically would name a
    channel nobody joined.
    """
    declared = type(scenario).postmortem_channel_ids
    agents = scenario.get_agents(default_model="m", default_provider="anthropic")
    for channel_id in sorted(declared):
        for agent in agents:
            if channel_id in agent.channel_ids:
                return channel_id, agent.agent_id
    raise AssertionError(f"{scenario.name()}: no declared postmortem channel has a member")


def a_member_of(scenario: SimulationScenario, channel_id: str) -> str:
    """Return an agent that belongs to ``channel_id``."""
    for agent in scenario.get_agents(default_model="m", default_provider="anthropic"):
        if channel_id in agent.channel_ids:
            return agent.agent_id
    raise AssertionError(f"{scenario.name()}: nobody is in {channel_id}")


@pytest.mark.parametrize("scenario_name", POSTMORTEM_SCENARIOS)
def test_the_discussion_channel_is_shut_until_the_phase_opens(scenario_name: str) -> None:
    """Before the phase, a debrief message must be refused with a reason."""
    overrides = fast_round_overrides(round_count=2)
    overrides["postmortem_enabled"] = True
    scenario = build_scenario(scenario_name=scenario_name, overrides=overrides)
    channel_id, agent_id = a_live_postmortem_channel(scenario=scenario)

    rejection = scenario.validate_outgoing_message(agent_id=agent_id, channel_id=channel_id)

    assert rejection is not None, "the discussion channel accepted traffic before the phase opened"
    assert rejection.strip(), "refused the message without saying why"


@pytest.mark.parametrize("scenario_name", POSTMORTEM_SCENARIOS)
def test_opening_the_phase_opens_the_discussion_channel(scenario_name: str) -> None:
    """`on_postmortem_started` is the only thing that flips this."""
    overrides = fast_round_overrides(round_count=2)
    overrides["postmortem_enabled"] = True
    scenario = build_scenario(scenario_name=scenario_name, overrides=overrides)
    channel_id, agent_id = a_live_postmortem_channel(scenario=scenario)

    scenario.on_postmortem_started(round_number=1)

    assert scenario.get_world().in_postmortem, "the world did not record that the phase began"
    assert (
        scenario.validate_outgoing_message(agent_id=agent_id, channel_id=channel_id) is None
    ), "the discussion channel stayed shut after the phase opened"


@pytest.mark.parametrize("scenario_name", POSTMORTEM_SCENARIOS)
def test_the_primary_channel_closes_during_the_phase(scenario_name: str) -> None:
    """The debrief is meant to interrupt the task, not run alongside it."""
    overrides = fast_round_overrides(round_count=2)
    overrides["postmortem_enabled"] = True
    scenario = build_scenario(scenario_name=scenario_name, overrides=overrides)
    primaries = scenario.get_primary_channels()
    if not primaries:
        pytest.skip("scenario scores no primary channel in this configuration")
    channel_id = primaries[0].channel_id
    agent_id = a_member_of(scenario=scenario, channel_id=channel_id)
    assert scenario.validate_outgoing_message(agent_id=agent_id, channel_id=channel_id) is None

    scenario.on_postmortem_started(round_number=1)

    assert (
        scenario.validate_outgoing_message(agent_id=agent_id, channel_id=channel_id) is not None
    ), "the task channel stayed open during the debrief"


@pytest.mark.parametrize("scenario_name", POSTMORTEM_SCENARIOS)
def test_a_globally_disabled_postmortem_stays_shut_even_when_the_phase_opens(
    scenario_name: str,
) -> None:
    """`set_postmortem` mid-run closes the channel for good, phase or not."""
    overrides: dict[str, object] = {"postmortem_enabled": True}
    scenario = build_scenario(scenario_name=scenario_name, overrides=overrides)
    channel_id, agent_id = a_live_postmortem_channel(scenario=scenario)

    scenario.get_world().disable_postmortem_globally()
    scenario.on_postmortem_started(round_number=1)

    assert (
        scenario.validate_outgoing_message(agent_id=agent_id, channel_id=channel_id) is not None
    ), "a globally disabled discussion channel accepted traffic"


@pytest.mark.parametrize("scenario_name", POSTMORTEM_SCENARIOS)
def test_closing_the_phase_reopens_the_task_channel(scenario_name: str) -> None:
    """A phase that opens and never closes locks the task channel for the run.

    Scenarios close it from `on_round_advanced`. Nothing else reads the flag,
    so without this a world that only ever sets the phase on still passes: the
    next round's messages are all refused and the run reports empty rounds.
    """
    overrides = fast_round_overrides(round_count=2)
    overrides["postmortem_enabled"] = True
    scenario = build_scenario(scenario_name=scenario_name, overrides=overrides)
    primaries = scenario.get_primary_channels()
    if not primaries:
        pytest.skip("scenario scores no primary channel in this configuration")
    channel_id = primaries[0].channel_id
    agent_id = a_member_of(scenario=scenario, channel_id=channel_id)
    world = scenario.get_world()

    scenario.on_postmortem_started(round_number=1)
    assert scenario.validate_outgoing_message(agent_id=agent_id, channel_id=channel_id) is not None
    world.exit_postmortem()

    assert not world.in_postmortem, "the world still reports the phase as open"
    assert (
        scenario.validate_outgoing_message(agent_id=agent_id, channel_id=channel_id) is None
    ), "the task channel stayed shut after the debrief ended"


@pytest.mark.parametrize("scenario_name", POSTMORTEM_SCENARIOS)
async def test_the_phase_is_shut_again_before_the_next_round_begins(
    scenario_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clock opens the phase and the clock shuts it, at every round advance.

    Nothing in a run's output observes this. Scripted agents have spent their
    scripts by the time the first phase opens, so a task channel left shut from
    round two onward changes no event the run records: removing the close from
    the clock entirely leaves the whole suite passing, while in a real run every
    round after the first would silently refuse its traffic.

    So the phase is read at the moment the scenario's round-advance hook runs,
    which is the point the clock has just passed. Reading it at the end of the
    run instead would prove nothing, because the final round's phase opens with
    no round after it to shut it.
    """
    overrides = fast_round_overrides(round_count=2)
    overrides["postmortem_enabled"] = True
    scenario = build_scenario(scenario_name=scenario_name, overrides=overrides)
    world = scenario.get_world()
    seen_open_at_advance: list[int] = []
    advanced = scenario.on_round_advanced

    async def record_then_advance(round_number: int) -> None:
        if world.in_postmortem:
            seen_open_at_advance.append(round_number)
        await advanced(round_number=round_number)

    monkeypatch.setattr(scenario, "on_round_advanced", record_then_advance)

    result = await run_scenario(
        scenario=scenario, round_count=2, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    assert result.of_type(event_type="postmortem_started"), "no phase ever opened"
    assert not seen_open_at_advance, (
        f"rounds {seen_open_at_advance} began with the discussion phase still open, "
        "so their task channel refused every message"
    )
