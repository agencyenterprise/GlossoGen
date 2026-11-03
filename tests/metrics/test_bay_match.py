"""``bay_match`` over move_a_box rounds played by scripted operators."""

from pathlib import Path

import pytest

from glossogen.evaluation.metric_core.measurement import Measurement
from glossogen.evaluation.metric_core.metric_protocol import Metric
from glossogen.evaluation.metric_core.metric_run_options import MetricRunOptions
from glossogen.models.event import SimulationEvent
from glossogen.scenarios.move_a_box.evaluation.bay_match_metric import BayMatchMetric
from glossogen.scenarios.move_a_box.ids import OPERATOR_A, OPERATOR_B
from glossogen.scenarios.move_a_box.scenario import MoveABoxScenario
from glossogen.testing.scripted_agent import ScriptedTurn
from glossogen.testing.stub_llm_provider import StubLLMProvider
from tests.scenarios.move_a_box.move_a_box_play import (
    ONE_ROUND,
    OPERATORS,
    TO_BAY_THREE,
    TWO_TARGETS,
    bay_cell,
    build,
    finish,
    first_depot,
    haul_path,
    play,
    read,
    second_target,
    to_shared_bay,
    two_target_scripts,
    wait_for_next_round,
)

pytestmark = pytest.mark.xdist_group("move_a_box")


async def measure(
    metric: Metric,
    scenario: MoveABoxScenario,
    events: list[SimulationEvent],
    tmp_path: Path,
) -> list[Measurement]:
    return await metric.compute(
        events=events,
        agent_configs=scenario.get_agents(default_model="test", default_provider="self-hosted"),
        scenario=scenario,
        llm_provider=StubLLMProvider(),
        run_dir=tmp_path,
        options=MetricRunOptions(probe_round=None, probe_replicas=1, ontology_path=None),
    )


async def test_bay_match_scores_one_for_a_round_on_the_same_bay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        agent_id: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()]
        for agent_id in (OPERATOR_A, OPERATOR_B)
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [measurement] = await measure(
        metric=BayMatchMetric(), scenario=scenario, events=result.events, tmp_path=tmp_path
    )
    assert measurement.score == 1.0
    assert [observation.value for observation in measurement.per_agent] == [1.0, 1.0]


async def test_bay_match_separates_delivering_from_agreeing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both deliver and neither agrees: the score is 0 while both delivery rates are 1."""
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    scripts: dict[str, list[ScriptedTurn]] = {
        OPERATOR_A: [read(), *to_shared_bay(method="cart"), finish(), wait_for_next_round()],
        OPERATOR_B: [
            read(),
            *haul_path(directions=TO_BAY_THREE, method="cart"),
            finish(),
            wait_for_next_round(),
        ],
    }
    result = await play(
        scenario=scenario, scripts=scripts, tmp_path=tmp_path, monkeypatch=monkeypatch
    )

    [measurement] = await measure(
        metric=BayMatchMetric(), scenario=scenario, events=result.events, tmp_path=tmp_path
    )
    assert measurement.score == 0.0
    assert [observation.value for observation in measurement.per_agent] == [1.0, 1.0]


async def test_bay_match_scores_each_target_of_a_round_that_holds_several(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missed first target and a matched second score the round 0.5; both still delivered."""
    scenario = build(preset_name="knobs_default", overrides=TWO_TARGETS)
    opening = first_depot(scenario=scenario).first_target
    first = {
        OPERATOR_A: bay_cell(target=opening, agent_id=OPERATOR_A, shared=False),
        OPERATOR_B: bay_cell(target=opening, agent_id=OPERATOR_B, shared=True),
    }
    target = second_target(scenario=scenario, crates=first)
    second = {
        agent_id: bay_cell(target=target, agent_id=agent_id, shared=True) for agent_id in OPERATORS
    }
    result = await play(
        scenario=scenario,
        scripts=two_target_scripts(first=first, second=second),
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )

    [measurement] = await measure(
        metric=BayMatchMetric(), scenario=scenario, events=result.events, tmp_path=tmp_path
    )
    assert measurement.score == 0.5
    assert measurement.score_unit == "share of targets whose crates ended on one bay"
    assert measurement.summary.startswith("1/2 targets matched. 0/1 rounds matched every target.")
    assert [observation.value for observation in measurement.per_agent] == [1.0, 1.0]


async def test_bay_match_skips_a_run_with_no_rounds(tmp_path: Path) -> None:
    scenario = build(preset_name="knobs_default", overrides=ONE_ROUND)
    assert (
        await measure(metric=BayMatchMetric(), scenario=scenario, events=[], tmp_path=tmp_path)
        == []
    )
