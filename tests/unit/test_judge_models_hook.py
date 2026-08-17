"""What `get_judge_models` answers, and why a launch believes it.

A scenario that judges its own rounds calls a model its agents never call, under
a provider its own knobs name. The launch check asks this hook what those models
are, so the hook is the only thing that decides whether a run needs a credential
for a judge.

That makes its answer authoritative rather than advisory. A configuration that
calls no judge says so by overriding this, and nothing second-guesses it: a
conformance check that compared the answer against the presence of the knobs
would fail a scenario for exactly that, and would also fail one that named its
knobs something else, which the hook explicitly invites.
"""

from glossogen.scenario_loader import get_scenario_class
from glossogen.scenario_protocol import SimulationScenario
from glossogen.scenarios.base_knobs import BaseKnobs


class DefaultedJudgeKnobs(BaseKnobs):
    """Judge knobs carrying declared defaults, which no scenario here does.

    Every judge knob shipped in this repository is required, so a preset that
    omits one is rejected before anything reads it. A scenario in another
    package is free to give them defaults, and then a preset may legitimately
    omit them.
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


class SilentJudgeScenario(ScenarioWithDefaultedJudge):
    """A scenario whose judge is configured but never called.

    The shape the launch check has to believe: knobs that name a judge, and a
    configuration that scores its rounds without one. Reporting nothing here is
    what keeps the run from demanding a credential it will not spend.
    """

    @classmethod
    def get_judge_models(cls, knobs: dict[str, object] | None) -> tuple[()]:
        """Report no judge, whatever the knobs say."""
        _ = knobs
        return ()


def test_the_hook_lives_on_the_contract_so_external_scenarios_inherit_it() -> None:
    """A scenario in another package gets the default without declaring anything."""
    assert callable(SimulationScenario.get_judge_models)


def test_it_reports_the_configured_judge() -> None:
    """The pair every scenario here names, read from the config it was launched with."""
    scenario_cls = get_scenario_class(name="veyru")
    config = scenario_cls.load_knobs_preset(preset_name="knobs_default")
    declared = scenario_cls.get_judge_models(knobs=config)
    assert [(entry.model, entry.provider) for entry in declared] == [
        (config["judge_model"], config["judge_provider"])
    ]


def test_a_scenario_that_scores_without_a_judge_reports_none() -> None:
    """No judge knobs, no judge: the launch check asks for nothing on its behalf."""
    assert get_scenario_class(name="prisoners_dilemma").get_judge_models(knobs={}) == ()


def test_an_omitted_knob_with_a_default_resolves_to_it() -> None:
    """A preset may leave a defaulted knob out, and the hook still reports it."""
    assert (
        ScenarioWithDefaultedJudge.resolve_str_knob(knobs={}, field_name="judge_model")
        == "default-judge"
    )
    declared = ScenarioWithDefaultedJudge.get_judge_models(knobs={})
    assert [(entry.model, entry.provider) for entry in declared] == [("default-judge", "anthropic")]


def test_a_scenario_may_report_no_judge_despite_naming_one() -> None:
    """The override that a conformance check used to refuse.

    A judge switched off by another knob, or one reached only in a mode a preset
    turns off, is a configuration that calls no model of its own. The hook is
    where that is stated, and stating it must not cost the scenario its contract.
    """
    assert SilentJudgeScenario.get_judge_models(knobs={"judge_model": "unused"}) == ()
