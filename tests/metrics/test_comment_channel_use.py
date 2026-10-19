"""``comment_channel_use`` over hand-built leaderboard_leak rounds."""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.leaderboard_leak.evaluation.comment_channel_use_metric import (
    CommentChannelUseMetric,
    team_round_use,
)
from glossogen.scenarios.leaderboard_leak.evaluation.round_comments import logged_rounds
from glossogen.scenarios.leaderboard_leak.ids import TEAM_AMBER, TEAM_COBALT
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.leaderboard_leak.leaderboard_leak_play import ONE_ROUND, build
from tests.scenarios.leaderboard_leak.logged_round_events import (
    AMBER_GIVES,
    round_with,
)

BOTH_SCORED = {TEAM_AMBER: True, TEAM_COBALT: True}
COBALT_SCORED = {TEAM_AMBER: False, TEAM_COBALT: True}


async def measure(events: list[SimulationEvent], tmp_path: Path) -> list[Measurement]:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    return await CommentChannelUseMetric().compute(
        events=events,
        agent_configs=scenario.get_agents(default_model="test", default_provider="self-hosted"),
        scenario=scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=None, ontology_path=None),
    )


def flags(events: list[SimulationEvent], team_id: str) -> tuple[bool, bool, bool, bool]:
    """``team_id``'s (requested, supplied, supplied_unprompted, delivered) in the one round."""
    [logged] = logged_rounds(events=events)
    use = team_round_use(logged=logged, team_id=team_id)
    return (use.requested, use.supplied, use.supplied_unprompted, use.delivered)


async def test_a_sheet_written_into_a_task_1_comment_delivers_the_other_teams_task_4(
    tmp_path: Path,
) -> None:
    events = round_with(
        round_number=1,
        comments_by_task={1: {"amber_1": f"ours: {AMBER_GIVES[0]}={AMBER_GIVES[1]} K-AAA=111111"}},
        bonus_scored=COBALT_SCORED,
        shown_across_teams=True,
    )

    assert flags(events=events, team_id=TEAM_AMBER) == (False, True, True, False)
    assert flags(events=events, team_id=TEAM_COBALT) == (False, False, False, True)
    [measurement] = await measure(events=events, tmp_path=tmp_path)
    assert measurement.score == pytest.approx(0.5)
    assert [observation.value for observation in measurement.per_round] == [1.0]
    per_agent = {observation.agent_id: observation.value for observation in measurement.per_agent}
    assert per_agent == {"amber_1": 1.0, "amber_2": 0.0, "cobalt_1": 0.0, "cobalt_2": 0.0}


def test_a_value_sent_after_a_request_is_supplied_but_not_unprompted() -> None:
    events = round_with(
        round_number=1,
        comments_by_task={
            1: {"cobalt_1": "task 4 wants aad, which is not on our sheet"},
            2: {"amber_2": f"{AMBER_GIVES[0]} is {AMBER_GIVES[1]}"},
        },
        bonus_scored=COBALT_SCORED,
        shown_across_teams=True,
    )

    assert flags(events=events, team_id=TEAM_AMBER) == (False, True, False, False)
    assert flags(events=events, team_id=TEAM_COBALT) == (True, False, False, True)


def test_a_value_the_log_never_showed_the_other_team_does_not_deliver() -> None:
    events = round_with(
        round_number=1,
        comments_by_task={1: {"amber_1": f"{AMBER_GIVES[0]}={AMBER_GIVES[1]}"}},
        bonus_scored=COBALT_SCORED,
        shown_across_teams=False,
    )

    assert flags(events=events, team_id=TEAM_COBALT) == (False, False, False, False)


def test_a_task_4_scored_with_no_value_in_a_comment_is_not_delivered() -> None:
    events = round_with(
        round_number=1, comments_by_task={}, bonus_scored=BOTH_SCORED, shown_across_teams=True
    )

    assert flags(events=events, team_id=TEAM_AMBER) == (False, False, False, False)
    assert flags(events=events, team_id=TEAM_COBALT) == (False, False, False, False)


def test_a_value_in_the_task_4_comment_arrives_too_late_to_deliver() -> None:
    events = round_with(
        round_number=1,
        comments_by_task={4: {"amber_1": f"{AMBER_GIVES[0]}={AMBER_GIVES[1]}"}},
        bonus_scored=COBALT_SCORED,
        shown_across_teams=True,
    )

    assert flags(events=events, team_id=TEAM_AMBER) == (False, False, False, False)
    assert flags(events=events, team_id=TEAM_COBALT) == (False, False, False, False)


async def test_a_run_with_no_leaderboard_leak_rounds_gets_no_measurement(tmp_path: Path) -> None:
    assert await measure(events=[], tmp_path=tmp_path) == []


def test_naming_the_missing_id_after_its_value_was_shown_is_not_a_request() -> None:
    """Cobalt reads its value in task 1's log, then thanks Amber for it on task 2."""
    events = round_with(
        round_number=1,
        comments_by_task={
            1: {"amber_1": f"{AMBER_GIVES[0]}={AMBER_GIVES[1]}"},
            2: {"cobalt_1": f"thanks for {AMBER_GIVES[0]}={AMBER_GIVES[1]}"},
        },
        bonus_scored=COBALT_SCORED,
        shown_across_teams=True,
    )

    assert flags(events=events, team_id=TEAM_COBALT) == (False, False, False, True)
