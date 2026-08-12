"""Noise has to land on the task channel and nowhere else.

Channel noise is the one knob that changes what an agent reads rather than what
it is told, so a scenario that wires it to the wrong channel produces a run that
looks healthy and measures nothing: the transcript is clean, the compression
metrics score an uncorrupted channel, and the experiment silently answers a
different question. Nothing else in the suite calls
``transform_outgoing_message``.

Each scenario implements its own corruption, so these are parametrized over the
registry rather than written once. A scenario that implements none is skipped
rather than failed: applying no channel noise is a fact about that scenario, not
a gap in it.
"""

import pytest

from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenario_registry import SCENARIO_REGISTRY
from tests.scenarios.scenario_runtime import build_scenario

ALL_SCENARIOS = sorted(SCENARIO_REGISTRY)

# Every character is corrupted at 1.0, so a single short message is enough to
# tell a noisy channel from a clean one without depending on a lucky draw.
TOTAL_NOISE = 1.0
MESSAGE = "hold position and confirm the sequence"


def build_noisy(scenario_name: str, level: float) -> SimulationScenario:
    """Build ``scenario_name`` from its shipped preset at a given noise level."""
    return build_scenario(scenario_name=scenario_name, overrides={"channel_noise_level": level})


def a_noisy_channel(scenario: SimulationScenario) -> str:
    """Return the channel this scenario corrupts, or skip if it corrupts none.

    A scenario applies noise to the channel it scores, so the primary channel is
    where to look. Scenarios that never implement the transform
    (``hospital_bed_assignment_privacy``, ``prisoners_dilemma``) apply their
    pressure some other way and have no noisy channel to check.
    """
    owns_transform = (
        type(scenario).transform_outgoing_message
        is not SimulationScenario.transform_outgoing_message
    )
    primaries = scenario.get_primary_channels()
    if not owns_transform or not primaries:
        pytest.skip("scenario applies no channel noise in this configuration")
    return primaries[0].channel_id


def a_member_of(scenario: SimulationScenario, channel_id: str) -> str:
    """Return an agent that belongs to ``channel_id``."""
    for agent in scenario.get_agents(default_model="m", default_provider="anthropic"):
        if channel_id in agent.channel_ids:
            return agent.agent_id
    raise AssertionError(f"{scenario.name()}: nobody is in {channel_id}")


@pytest.mark.parametrize("scenario_name", ALL_SCENARIOS)
def test_the_task_channel_is_corrupted_when_noise_is_on(scenario_name: str) -> None:
    """At full noise, nothing an agent sends on the task channel survives intact."""
    scenario = build_noisy(scenario_name=scenario_name, level=TOTAL_NOISE)
    channel_id = a_noisy_channel(scenario=scenario)
    agent_id = a_member_of(scenario=scenario, channel_id=channel_id)

    on_the_wire = scenario.transform_outgoing_message(
        agent_id=agent_id, channel_id=channel_id, text=MESSAGE
    )

    assert on_the_wire != MESSAGE, "the task channel delivered the message uncorrupted"
    assert len(on_the_wire) == len(MESSAGE), (
        "corruption changed the message length, which moves mean_chars_per_round "
        "without the agent sending any more"
    )


@pytest.mark.parametrize("scenario_name", ALL_SCENARIOS)
def test_the_discussion_channel_stays_clean(scenario_name: str) -> None:
    """The debrief is where agents compare notes, so it is never corrupted."""
    scenario = build_noisy(scenario_name=scenario_name, level=TOTAL_NOISE)
    a_noisy_channel(scenario=scenario)
    declared = sorted(type(scenario).postmortem_channel_ids)
    if not declared:
        pytest.skip("scenario has no postmortem channel")
    built = {channel.channel_id for channel in scenario.get_channels()}
    live = [channel_id for channel_id in declared if channel_id in built]
    if not live:
        pytest.skip("this configuration builds none of the declared postmortem channels")
    agent_id = a_member_of(scenario=scenario, channel_id=live[0])

    on_the_wire = scenario.transform_outgoing_message(
        agent_id=agent_id, channel_id=live[0], text=MESSAGE
    )

    assert on_the_wire == MESSAGE, "the discussion channel was corrupted"


@pytest.mark.parametrize("scenario_name", ALL_SCENARIOS)
def test_noise_off_leaves_the_message_alone(scenario_name: str) -> None:
    """The default is a lossless channel, which most runs depend on."""
    scenario = build_noisy(scenario_name=scenario_name, level=0.0)
    channel_id = a_noisy_channel(scenario=scenario)
    agent_id = a_member_of(scenario=scenario, channel_id=channel_id)

    assert (
        scenario.transform_outgoing_message(agent_id=agent_id, channel_id=channel_id, text=MESSAGE)
        == MESSAGE
    )


@pytest.mark.parametrize("scenario_name", ALL_SCENARIOS)
def test_the_same_seed_corrupts_the_same_way(scenario_name: str) -> None:
    """Two runs of one preset have to produce the same wire, or nothing replicates.

    Both scenarios are built from the same preset, so they share a seed. Drawing
    from a per-run stream rather than a shared one is what makes this hold.
    """
    first = build_noisy(scenario_name=scenario_name, level=0.5)
    second = build_noisy(scenario_name=scenario_name, level=0.5)
    channel_id = a_noisy_channel(scenario=first)
    agent_id = a_member_of(scenario=first, channel_id=channel_id)

    sent_by_first = [
        first.transform_outgoing_message(agent_id=agent_id, channel_id=channel_id, text=MESSAGE)
        for _ in range(5)
    ]
    sent_by_second = [
        second.transform_outgoing_message(agent_id=agent_id, channel_id=channel_id, text=MESSAGE)
        for _ in range(5)
    ]

    assert sent_by_first == sent_by_second, "the same seed produced a different corruption"
