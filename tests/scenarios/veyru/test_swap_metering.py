"""What the observer swap does to each team's budget.

The swap moves agents between links: after it fires, team A's link carries team
B's observer. A budget that followed the agent rather than the link would meter
a conversation happening somewhere else, and the Veyru on that link would
collapse on characters nobody spent there. Nothing about the run looks wrong
when that happens; the round just fails for the wrong reason.
"""

import pytest

from glossogen.scenarios.veyru.ids import (
    LINK_A_CHANNEL_ID,
    LINK_B_CHANNEL_ID,
    TEAM_A_ID,
    TEAM_B_ID,
)
from glossogen.scenarios.veyru.world import VeyruWorld
from tests.scenarios.scenario_runtime import build_scenario

SCENARIO = "veyru"

pytestmark = pytest.mark.xdist_group(SCENARIO)


def two_team_swap_world() -> VeyruWorld:
    """Build the world of a two-team veyru configured to swap its observers."""
    scenario = build_scenario(
        scenario_name=SCENARIO, overrides={"two_teams": True, "swap_round": 10}
    )
    world = scenario.get_world()
    assert isinstance(world, VeyruWorld)
    return world


def test_each_link_bills_its_own_team_after_the_observers_swap() -> None:
    """The observer that arrives spends the budget of the link it arrived on."""
    world = two_team_swap_world()
    arrived_on_a, arrived_on_b = world.swap_observers()
    world.begin_round()

    world.on_message(
        agent_id=arrived_on_a, channel_id=LINK_A_CHANNEL_ID, text="x" * 10, token_count=0
    )
    world.on_message(
        agent_id=arrived_on_b, channel_id=LINK_B_CHANNEL_ID, text="x" * 3, token_count=0
    )

    assert world.characters_used(team_id=TEAM_A_ID) == 10
    assert world.characters_used(team_id=TEAM_B_ID) == 3


def test_the_swap_puts_each_observer_on_the_other_link() -> None:
    """The premise of the test above, asserted rather than assumed.

    If a future swap moved channels instead of agents, the metering test would
    still pass while covering nothing.
    """
    world = two_team_swap_world()
    before_a = world.teams[TEAM_A_ID].current_observer_id
    before_b = world.teams[TEAM_B_ID].current_observer_id

    arrived_on_a, arrived_on_b = world.swap_observers()

    assert arrived_on_a == before_b, "team A's link did not receive team B's observer"
    assert arrived_on_b == before_a, "team B's link did not receive team A's observer"
    assert (
        world.teams[TEAM_A_ID].link_channel_id == LINK_A_CHANNEL_ID
    ), "the link moved, not the agent"
