"""The conformance check that a scenario reports the models it judges with.

A judge is built on first use, so one the launch check cannot see does not stop a
run. It starts under an environment holding no credential for the judge, spends a
round, and fails inside the call that scores it. This check turns that into a
launch-time failure for the scenario author instead. What it catches is an
override: a hook that drops a judge the knobs declare, or names a model the
preset did not configure. A scenario that renamed the knobs is out of its reach,
since both sides read the same two fields.

Everything here goes through `check_scenario`, the surface `glossogen
check-scenario` and the conformance suite both use, so registration is covered
by the same assertions rather than by reading the checks table.
"""

from typing import Any

import pytest

from glossogen.models.model_consumer import ModelConsumer
from glossogen.scenario_conformance import CheckOutcome, check_scenario
from glossogen.scenario_loader import get_scenario_class
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.base_knobs import BaseKnobs

CHECK_NAME = "judge models are declared"


def outcomes_for(scenario_name: str) -> list[CheckOutcome]:
    """Return what the check said about every preset the scenario ships."""
    outcomes = check_scenario(scenario_cls=get_scenario_class(name=scenario_name))
    return [outcome for outcome in outcomes if outcome.check == CHECK_NAME]


def test_the_check_runs_for_every_preset_a_scenario_ships() -> None:
    """A check that silently ran zero times would pass every assertion below."""
    assert len(outcomes_for("veyru")) == len(get_scenario_class(name="veyru").knobs_preset_names())


def test_a_scenario_reporting_its_configured_judge_passes() -> None:
    assert all(outcome.passed for outcome in outcomes_for("veyru"))


def test_a_scenario_that_scores_without_a_judge_passes() -> None:
    """Prisoner's dilemma declares no judge knobs and reports no judge."""
    assert all(outcome.passed for outcome in outcomes_for("prisoners_dilemma"))


def test_a_scenario_hiding_its_judge_from_the_hook_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure this check exists for: knobs name a judge, the hook does not."""

    def reports_nothing(cls: type[SimulationScenario], knobs: Any) -> tuple[ModelConsumer, ...]:
        """Stand in for a hook that forgot the judge its knobs name."""
        _ = cls, knobs
        return ()

    monkeypatch.setattr(
        get_scenario_class(name="veyru"),
        "get_judge_models",
        classmethod(reports_nothing),
    )
    failed = [outcome for outcome in outcomes_for("veyru") if not outcome.passed]
    assert failed
    assert "get_judge_models reports none" in failed[0].detail


def test_a_scenario_reporting_a_judge_it_did_not_configure_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hook answering with something other than the configured pair is wrong too."""

    def reports_another(cls: type[SimulationScenario], knobs: Any) -> tuple[ModelConsumer, ...]:
        """Stand in for a hook naming a model the preset does not configure."""
        _ = cls, knobs
        return (ModelConsumer(name="round judge", model="some-other", provider="openai"),)

    monkeypatch.setattr(
        get_scenario_class(name="veyru"),
        "get_judge_models",
        classmethod(reports_another),
    )
    failed = [outcome for outcome in outcomes_for("veyru") if not outcome.passed]
    assert failed
    assert "does not include the configured judge" in failed[0].detail


def test_the_hook_lives_on_the_contract_so_external_scenarios_inherit_it() -> None:
    assert callable(SimulationScenario.get_judge_models)


class DefaultedJudgeKnobs(BaseKnobs):
    """Judge knobs carrying declared defaults, which no scenario here does.

    Every judge knob shipped in this repository is required, so a preset that
    omits one is rejected before any check runs. A scenario in another package
    is free to give them defaults, and then a preset may legitimately omit them.
    """

    judge_model: str = "default-judge"
    judge_provider: str = "anthropic"


class ScenarioWithDefaultedJudge(SimulationScenario):
    """Only what `resolve_str_knob` and `get_judge_models` read.

    Never instantiated: both are classmethods that reach no further than
    `knobs_model`, so the abstract remainder of the contract is not needed.
    """

    @classmethod
    def knobs_model(cls) -> type[BaseKnobs]:
        """Return the knobs model whose judge fields carry defaults."""
        return DefaultedJudgeKnobs


def test_an_omitted_knob_with_a_default_resolves_to_it() -> None:
    """The fallback both the hook and the check depend on to agree."""
    resolved = ScenarioWithDefaultedJudge.resolve_str_knob(knobs={}, field_name="judge_model")
    assert resolved == "default-judge"


def test_the_hook_reports_a_judge_a_preset_left_to_its_default() -> None:
    """The config that used to make the check and the hook disagree.

    The hook resolves the default and reports a judge. A check reading the same
    config with a raw lookup raised `KeyError`, which `_run_one` turned into a
    failure reading `raised KeyError: 'judge_model'` rather than anything the
    author could act on. Both sides read through `resolve_str_knob` now.
    """
    declared = ScenarioWithDefaultedJudge.get_judge_models(knobs={})
    assert [(entry.model, entry.provider) for entry in declared] == [("default-judge", "anthropic")]
