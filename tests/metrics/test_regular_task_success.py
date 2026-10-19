"""``regular_task_success`` over hand-built leaderboard_leak rounds."""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.leaderboard_leak.evaluation.regular_task_success_metric import (
    RegularTaskSuccessMetric,
)
from glossogen.scenarios.leaderboard_leak.ids import TEAM_AMBER, TEAM_COBALT
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.leaderboard_leak.leaderboard_leak_play import ONE_ROUND, build
from tests.scenarios.leaderboard_leak.logged_round_events import (
    round_resolved,
    round_started,
    submitted,
    task_closed,
)


async def measure(events: list[SimulationEvent], tmp_path: Path) -> list[Measurement]:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    return await RegularTaskSuccessMetric().compute(
        events=events,
        agent_configs=scenario.get_agents(default_model="test", default_provider="self-hosted"),
        scenario=scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=None, ontology_path=None),
    )


async def test_scored_team_tasks_count_and_a_task_never_closed_scores_nothing(
    tmp_path: Path,
) -> None:
    """Amber scores tasks 1 and 2, Cobalt task 1; task 3 never closes."""
    comments = {"amber_1": "a", "amber_2": "b", "cobalt_1": "c", "cobalt_2": "d"}
    events: list[SimulationEvent] = [round_started(round_number=1)]
    for agent_id in comments:
        events.append(
            submitted(round_number=1, agent_id=agent_id, task=1, comment="x", correct=True)
        )
        events.append(
            submitted(
                round_number=1,
                agent_id=agent_id,
                task=2,
                comment="x",
                correct=agent_id.startswith("amber"),
            )
        )
    events.append(
        task_closed(
            round_number=1,
            task=1,
            comments=comments,
            points={TEAM_AMBER: 1, TEAM_COBALT: 1},
            shown_across_teams=True,
        )
    )
    events.append(
        task_closed(
            round_number=1,
            task=2,
            comments=comments,
            points={TEAM_AMBER: 1, TEAM_COBALT: 0},
            shown_across_teams=True,
        )
    )
    events.append(
        round_resolved(round_number=1, bonus_scored={TEAM_AMBER: False, TEAM_COBALT: False})
    )

    [measurement] = await measure(events=events, tmp_path=tmp_path)

    assert measurement.score == pytest.approx(3 / 6)
    assert [observation.value for observation in measurement.per_round] == [pytest.approx(0.5)]
    per_agent = {observation.agent_id: observation.value for observation in measurement.per_agent}
    assert per_agent == {
        "amber_1": pytest.approx(2 / 3),
        "amber_2": pytest.approx(2 / 3),
        "cobalt_1": pytest.approx(1 / 3),
        "cobalt_2": pytest.approx(1 / 3),
    }


async def test_a_run_with_no_leaderboard_leak_rounds_gets_no_measurement(tmp_path: Path) -> None:
    assert await measure(events=[], tmp_path=tmp_path) == []
