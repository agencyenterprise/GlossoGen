"""What a team is charged under each ``team_characters`` rule, live and on resume.

The rules themselves are checked on the world directly, where the order of
messages and submissions is the test's. Played rounds check the budget notices
that name the busiest member, and that a resume, whether the round ended or not,
charges each team what the live world did.
"""

from pathlib import Path

import pytest

from glossogen.models.event import RoundEnded, WorldEventDelivered
from glossogen.scenarios.spot_the_intersection.ids import BUDGET_EXCEEDED_MARKER, BUDGET_LOW_MARKER
from glossogen.scenarios.spot_the_intersection.scenario import SpotTheIntersectionScenario
from glossogen.testing.scripted_agent import SayTurn, ScriptedTurn
from glossogen.testing.simulation_harness import never_times_out, resume_simulation
from tests.scenarios.spot_the_intersection.conftest import (
    SCENARIO,
    TEAM_A,
    TEAM_B,
    answer_of,
    one_to_one_scenario,
    play,
    say_to,
    submit,
    world_of,
)

pytestmark = pytest.mark.xdist_group(SCENARIO)

BUDGET = 20


def direct(sender: str, recipient: str) -> str:
    """The direct channel id the runtime gives two viewers."""
    return "dm:" + "+".join(sorted((sender, recipient)))


@pytest.mark.parametrize(
    ("rule", "charged"), [("busiest_member", 10), ("total", 10 + 6 + 8)], ids=["busiest", "total"]
)
def test_a_team_is_charged_under_its_rule(rule: str, charged: int) -> None:
    scenario = one_to_one_scenario(overrides={"team_characters": rule})
    world = world_of(scenario=scenario)
    answer = answer_of(scenario=scenario)
    world.finalize_round_sync(round_number=1)
    for sender, recipient, length in ((0, 1, 10), (1, 2, 6), (2, 3, 8)):
        world.on_message(
            agent_id=TEAM_A[sender],
            channel_id=direct(sender=TEAM_A[sender], recipient=TEAM_A[recipient]),
            text="x" * length,
            token_count=1,
        )
    for agent_id in TEAM_A:
        world.record_submission(agent_id=agent_id, obj=answer)
    world.mark_round_outcome(round_number=1)

    outcome = world.outcome_for(team_id="team_a", round_number=1)
    assert outcome is not None
    assert outcome.characters_used == charged
    assert world.characters_used(team_id="team_a") == 10 + 6 + 8


def test_a_busiest_member_budget_caps_each_member_not_the_team() -> None:
    """Two members at 15 of 20 is 30 between them and still within budget; one at 20 is not."""
    scenario = one_to_one_scenario(overrides={"round_time_budget_seconds": BUDGET})
    world = world_of(scenario=scenario)
    answer = answer_of(scenario=scenario)
    world.finalize_round_sync(round_number=1)
    for agent_id in TEAM_B:
        world.record_submission(agent_id=agent_id, obj=answer)
    world.on_message(
        agent_id=TEAM_A[0],
        channel_id=direct(sender=TEAM_A[0], recipient=TEAM_A[1]),
        text="x" * 15,
        token_count=1,
    )
    world.on_message(
        agent_id=TEAM_A[1],
        channel_id=direct(sender=TEAM_A[1], recipient=TEAM_A[2]),
        text="y" * 15,
        token_count=1,
    )
    assert not world.all_teams_done()

    world.on_message(
        agent_id=TEAM_A[0],
        channel_id=direct(sender=TEAM_A[0], recipient=TEAM_A[2]),
        text="z" * 5,
        token_count=1,
    )

    assert world.all_teams_done()


async def test_budget_notices_name_the_busiest_member_and_a_rebuild_scores_the_same(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """viewer_b_1 sends 16 then 8 of 20 characters and Team B never submits; Team A locks."""
    scenario = one_to_one_scenario(overrides={"round_time_budget_seconds": BUDGET})
    answer = answer_of(scenario=scenario)
    scripts: dict[str, list[ScriptedTurn]] = {agent: [submit(obj=answer)] for agent in TEAM_A}
    scripts[TEAM_B[0]] = [
        say_to(to=TEAM_B[1], text="x" * 16),
        say_to(to=TEAM_B[2], text="y" * 8),
    ]

    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    notices = [
        event.text
        for event in result.of_type(event_type=WorldEventDelivered)
        if event.agent_id == TEAM_B[3]
    ]
    assert (
        f"{BUDGET_LOW_MARKER}. Viewer 1 (Team B) has sent 16 of the 20 characters each member "
        "may send." in notices
    )
    assert (
        f"{BUDGET_EXCEEDED_MARKER}. Viewer 1 (Team B) has sent 24 characters; each member's "
        "budget was 20. This round can no longer be won." in notices
    )
    rebuilt = SpotTheIntersectionScenario.create_from_config(
        config=scenario.get_knobs().model_dump(mode="json")
    )
    rebuilt.restore_state_from_events(events=result.events)
    for team_id in ("team_a", "team_b"):
        assert world_of(scenario=rebuilt).outcome_for(team_id=team_id, round_number=1) == world_of(
            scenario=result.scenario
        ).outcome_for(team_id=team_id, round_number=1)


async def test_a_resume_mid_round_keeps_what_each_member_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Members send 6 and 3 characters before the stop and 4 after: the team is charged 6.

    Restoring only a team total would charge 13, and restoring nothing would charge 4.
    """
    scenario = one_to_one_scenario(overrides={})
    answer = answer_of(scenario=scenario)
    before: dict[str, list[ScriptedTurn]] = {
        TEAM_A[0]: [say_to(to=TEAM_A[1], text="abcdef"), submit(obj=answer)],
        TEAM_A[1]: [say_to(to=TEAM_A[2], text="xyz"), submit(obj=answer)],
    }
    played = await play(
        scenario=scenario, scripts=before, tmp_path=tmp_path / "source", monkeypatch=monkeypatch
    )
    lines = played.log_path.read_text(encoding="utf-8").splitlines(keepends=True)
    stop = played.first_index(event_type=RoundEnded, round_number=1)
    resumed_dir = tmp_path / "resumed"
    resumed_dir.mkdir()
    (resumed_dir / f"{SpotTheIntersectionScenario.name()}.jsonl").write_text(
        "".join(lines[:stop]), encoding="utf-8"
    )

    after: dict[str, list[ScriptedTurn]] = {
        agent_id: [SayTurn(text="idle")] for agent_id in (*TEAM_A, *TEAM_B)
    }
    after[TEAM_A[2]] = [say_to(to=TEAM_A[3], text="abcd"), submit(obj=answer)]
    after[TEAM_A[3]] = [submit(obj=answer)]
    resumed = await resume_simulation(
        scenario=SpotTheIntersectionScenario.create_from_config(
            config=scenario.get_knobs().model_dump(mode="json")
        ),
        scripts=after,
        run_dir=resumed_dir,
        monkeypatch=monkeypatch,
        phase_timed_out=never_times_out,
    )

    outcome = world_of(scenario=resumed.scenario).outcome_for(team_id="team_a", round_number=1)
    assert outcome is not None
    assert outcome.members_submitted == 4
    assert outcome.correct
    assert outcome.characters_used == 6
