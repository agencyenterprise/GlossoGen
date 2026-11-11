"""The character budget and the lock decide what a team is charged.

A played run with a budget checks the notices, the early end and the verdict of
a team that spent its budget before every member submitted, and that a resume
rebuilds the same verdicts from the log. The metering rules themselves are
checked on the world directly, where the order of messages and submissions is
fixed by the test rather than by agent scheduling.
"""

from pathlib import Path

import pytest

from glossogen.models.event import RoundEnded, RoundResultRecorded, WorldEventDelivered
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenarios.spot_the_intersection.ids import (
    ALL_TEAMS_DONE_TRIGGER,
    BUDGET_EXCEEDED_MARKER,
    BUDGET_LOW_MARKER,
    ROUND_RESULT_MARKER,
)
from glossogen.scenarios.spot_the_intersection.scenario import SpotTheIntersectionScenario
from glossogen.testing.scenario_runtime import ROUND_SECONDS, build_scenario
from glossogen.testing.scripted_agent import ScriptedTurn
from tests.scenarios.spot_the_intersection.conftest import (
    SCENARIO,
    TEAM_A,
    TEAM_B,
    answer_of,
    one_round_scenario,
    play,
    say_on,
    submit,
    world_of,
)

pytestmark = pytest.mark.xdist_group(SCENARIO)

BUDGET = 20


def budgeted_scenario() -> SimulationScenario:
    """The two-team preset, one round with no debrief, and a 20-character budget."""
    return build_scenario(
        scenario_name=SCENARIO,
        preset_name="knobs_default",
        overrides={
            "round_count": 1,
            "max_round_duration_seconds": ROUND_SECONDS,
            "postmortem_enabled": False,
            "round_time_budget_seconds": BUDGET,
        },
    )


def notices_to(events: list[WorldEventDelivered], agent_id: str) -> list[str]:
    """Every world notice ``agent_id`` was sent."""
    return [event.text for event in events if event.agent_id == agent_id]


async def test_a_team_over_budget_is_told_so_and_ends_the_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Team B spends 16 then 24 of 20 characters and never submits; Team A locks."""
    scenario = budgeted_scenario()
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {agent: [submit(obj=answer)] for agent in TEAM_A}
    scripts[TEAM_B[0]] = [
        say_on(scenario=scenario, channel_id="link_b", text="x" * 16),
        say_on(scenario=scenario, channel_id="link_b", text="y" * 8),
    ]

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    (ended,) = result.of_type(event_type=RoundEnded)
    assert ended.trigger == ALL_TEAMS_DONE_TRIGGER
    verdicts = {
        verdict.team_id: verdict for verdict in result.of_type(event_type=RoundResultRecorded)
    }
    assert verdicts["team_a"].success is True
    assert verdicts["team_b"].success is False
    assert verdicts["team_b"].reason.startswith("over budget")
    delivered = result.of_type(event_type=WorldEventDelivered)
    team_b_notices = notices_to(events=delivered, agent_id=TEAM_B[1])
    assert any(text.startswith(BUDGET_LOW_MARKER) for text in team_b_notices)
    assert any(text.startswith(BUDGET_EXCEEDED_MARKER) for text in team_b_notices)
    assert any(
        text.startswith(f"{ROUND_RESULT_MARKER}. Communication budget exceeded")
        for text in team_b_notices
    )
    team_a_notices = notices_to(events=delivered, agent_id=TEAM_A[0])
    assert not any(text.startswith(BUDGET_LOW_MARKER) for text in team_a_notices)

    rebuilt = SpotTheIntersectionScenario.create_from_config(
        config=scenario.get_knobs().model_dump(mode="json")
    )
    rebuilt.restore_state_from_events(events=result.events)
    for team_id in ("team_a", "team_b"):
        assert world_of(scenario=rebuilt).outcome_for(team_id=team_id, round_number=1) == world_of(
            scenario=result.scenario
        ).outcome_for(team_id=team_id, round_number=1)


def test_link_messages_after_the_lock_are_not_charged() -> None:
    scenario = one_round_scenario()
    world = world_of(scenario=scenario)
    answer = answer_of(scenario=scenario)
    world.finalize_round_sync(round_number=1)
    world.on_message(agent_id=TEAM_A[0], channel_id="link_a", text="abc", token_count=1)
    for agent_id in TEAM_A:
        world.record_submission(agent_id=agent_id, obj=answer)

    world.on_message(
        agent_id=TEAM_A[0], channel_id="link_a", text="said after the lock", token_count=4
    )
    world.mark_round_outcome(round_number=1)

    outcome = world.outcome_for(team_id="team_a", round_number=1)
    assert outcome is not None
    assert outcome.characters_used == 3
    assert world.characters_used(team_id="team_a") == 3


def test_a_team_reaching_its_budget_is_done_without_submitting() -> None:
    scenario = budgeted_scenario()
    world = world_of(scenario=scenario)
    answer = answer_of(scenario=scenario)
    world.finalize_round_sync(round_number=1)
    for agent_id in TEAM_A:
        world.record_submission(agent_id=agent_id, obj=answer)
    assert not world.all_teams_done()

    world.on_message(agent_id=TEAM_B[0], channel_id="link_b", text="z" * BUDGET, token_count=5)

    assert world.all_teams_done()
