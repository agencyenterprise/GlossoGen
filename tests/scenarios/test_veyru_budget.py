"""Veyru's budget rule, driven at the boundary a real run never lands on.

Two properties here are invisible to every other test. A run's character total
lands wherever it lands and never exactly on the budget, so whether veyru
collapses at the budget or one character past it is not exercised. And the
outcome record's character count is never logged, so reading it after the
counters were cleared produces a run whose decision log is byte-identical and
whose recorded outcome is zero.

Both sit either side of the number the engine now meters, which is why they are
pinned here rather than left to the golden baseline that cannot see them.
"""

import json
from pathlib import Path
from typing import Any

from glossogen.scenario_loader import get_scenario_class
from glossogen.scenarios.veyru.ids import LINK_CHANNEL_ID, TEAM_SOLO_ID
from glossogen.scenarios.veyru.scenario import VeyruScenario
from glossogen.scenarios.veyru.world import (
    THRESHOLD_COLLAPSED,
    THRESHOLD_CRITICAL,
    VeyruWorld,
)

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "src" / "glossogen" / "scenarios"

# Veyru rejects postmortem_after_swap without postmortem_enabled, so the debrief
# is closed with both knobs together. With it open the postmortem injection
# computes each round's outcome early, which is the path that hides the ordering
# these check.
DEBRIEF_CLOSED: dict[str, Any] = {
    "two_teams": False,
    "postmortem_enabled": False,
    "postmortem_after_swap": False,
}


def build_veyru(overrides: dict[str, Any]) -> VeyruScenario:
    """Build veyru from its shipped preset plus overrides."""
    config = json.loads((SCENARIOS_DIR / "veyru" / "knobs_default.json").read_text())
    config.update(overrides)
    scenario_cls = get_scenario_class(name="veyru")
    built = scenario_cls.create_from_config(config=scenario_cls.prepare_config(config=dict(config)))
    assert isinstance(built, VeyruScenario)
    return built


def opened_round(overrides: dict[str, Any]) -> tuple[VeyruScenario, VeyruWorld, int]:
    """Return veyru with round one loaded, and that round's character budget."""
    scenario = build_veyru(overrides=overrides)
    world = scenario.get_world()
    assert isinstance(world, VeyruWorld)
    world.finalize_round_sync(round_number=1)
    case = world.current_case
    assert case is not None
    return scenario, world, case.time_budget_seconds


def spend(world: VeyruWorld, characters: int) -> None:
    """Send exactly ``characters`` characters on the solo team's comm link."""
    world.on_message(
        agent_id="field_observer",
        channel_id=LINK_CHANNEL_ID,
        text="x" * characters,
        token_count=0,
    )


def test_spending_exactly_the_budget_does_not_collapse_the_veyru() -> None:
    """The rule is 'past the budget', and a run never lands on the boundary."""
    _, world, budget = opened_round(overrides={"two_teams": False})

    spend(world=world, characters=budget)

    assert world.is_veyru_alive(
        team_id=TEAM_SOLO_ID
    ), "the Veyru collapsed on the budget rather than past it"


def test_spending_one_character_past_the_budget_collapses_it() -> None:
    """The other side of the same boundary."""
    _, world, budget = opened_round(overrides={"two_teams": False})

    spend(world=world, characters=budget + 1)

    assert not world.is_veyru_alive(team_id=TEAM_SOLO_ID)


def test_the_outcome_records_what_the_round_actually_spent() -> None:
    """The count has to survive until the outcome is built, then be cleared.

    Resetting the counters before the round's outcome is computed records every
    round as having spent nothing. Nothing in the event log shows it, so the run
    completes and the numbers are quietly wrong.
    """
    _, world, budget = opened_round(overrides=DEBRIEF_CLOSED)
    spent = budget - 1
    spend(world=world, characters=spent)

    world.finalize_round_sync(round_number=2)

    outcomes = world.get_outcomes_for_team(team_id=TEAM_SOLO_ID)
    assert outcomes, "round one produced no outcome"
    assert outcomes[-1].characters_used == spent
    assert outcomes[-1].time_elapsed_seconds == spent


def test_the_next_round_starts_from_zero() -> None:
    """The other half of the same ordering: the counter must not carry over."""
    _, world, budget = opened_round(overrides=DEBRIEF_CLOSED)
    spend(world=world, characters=budget - 1)

    world.finalize_round_sync(round_number=2)

    assert world.characters_used(team_id=TEAM_SOLO_ID) == 0


def test_the_warning_is_announced_before_the_collapse_and_neither_is_swallowed() -> None:
    """Veyru declares its thresholds most severe first, and the order is load-bearing.

    Declared the other way round, the CRITICAL warning would also claim the
    collapse, and a Veyru that warned before it died would die silently. The
    engine's ordering rule is exercised elsewhere; what this pins is that veyru
    hands it the order that rule expects.
    """
    _, world, _ = opened_round(overrides={"two_teams": False})

    warned = world.claim_round_budget_threshold(
        team_id=TEAM_SOLO_ID, round_budget_threshold=THRESHOLD_CRITICAL
    )
    collapsed = world.claim_round_budget_threshold(
        team_id=TEAM_SOLO_ID, round_budget_threshold=THRESHOLD_COLLAPSED
    )

    assert warned, "the first warning was already claimed"
    assert collapsed, "warning the team also swallowed its collapse announcement"


def test_the_collapse_announcement_suppresses_a_later_warning() -> None:
    """Telling a team it is running low after telling it the budget is gone reads backwards."""
    _, world, _ = opened_round(overrides={"two_teams": False})

    collapsed = world.claim_round_budget_threshold(
        team_id=TEAM_SOLO_ID, round_budget_threshold=THRESHOLD_COLLAPSED
    )
    warned = world.claim_round_budget_threshold(
        team_id=TEAM_SOLO_ID, round_budget_threshold=THRESHOLD_CRITICAL
    )

    assert collapsed
    assert not warned, "a collapsed Veyru was then warned it was running low"
