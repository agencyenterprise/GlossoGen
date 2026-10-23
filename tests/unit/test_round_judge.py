"""``ScenarioBase.round_judge`` exists exactly for scenarios whose knobs declare a judge."""

import pytest

from glossogen.llm.deferred_provider import DeferredLLMProvider
from glossogen.testing.scenario_runtime import build_scenario


def test_a_judged_scenario_gets_one_judge_built_from_its_knobs() -> None:
    scenario = build_scenario(scenario_name="veyru", preset_name="knobs_default", overrides={})

    judge = scenario.round_judge

    assert isinstance(judge, DeferredLLMProvider)
    assert scenario.round_judge is judge, "the judge is built once per scenario"
    assert [cost.model for cost in scenario.judge_costs()] == [
        scenario.get_knobs().model_dump()["judge_model"]
    ]


def test_a_scenario_without_judge_knobs_has_no_judge_and_bills_nothing() -> None:
    scenario = build_scenario(
        scenario_name="prisoners_dilemma", preset_name="knobs_default", overrides={}
    )

    assert scenario.judge_costs() == []
    with pytest.raises(TypeError):
        _ = scenario.round_judge
