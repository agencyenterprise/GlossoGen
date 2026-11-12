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


@pytest.mark.parametrize(
    "scenario_name",
    ["veyru", "orbital_anomaly", "drive_module_repair", "spot_the_difference"],
)
def test_these_judges_send_no_sampling_settings_unless_the_run_sets_them(
    scenario_name: str,
) -> None:
    """Their presets judge with Anthropic, whose API version 2026-10-21 refuses `temperature`.

    A default temperature made every judge call fail with a 400, so every
    submission scored as nothing found.
    """
    default = build_scenario(scenario_name=scenario_name, preset_name="knobs_default", overrides={})
    chosen = build_scenario(
        scenario_name=scenario_name,
        preset_name="knobs_default",
        overrides={"judge_model_settings": {"thinking": "low"}},
    )

    assert default.get_knobs().model_dump()["judge_model_settings"] == {}
    assert chosen.get_knobs().model_dump()["judge_model_settings"] == {"thinking": "low"}
