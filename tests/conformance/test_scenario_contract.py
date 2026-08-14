"""Every registered scenario, against every knobs preset it ships.

The checks themselves live in `glossogen.scenario_conformance`, because a
scenario can ship from any distribution and this suite does not: an author
outside this repository runs the same rules through
`glossogen check-scenario <name>`. What is left here is running them over the
built-ins, so a new scenario is covered the moment it is registered and a new
rule applies to every existing one.
"""

import pytest

from glossogen.scenario_conformance import CheckOutcome, check_scenario, failures
from glossogen.scenario_loader import get_scenario_class
from glossogen.scenario_registry import SCENARIO_REGISTRY

SCENARIO_NAMES = sorted(SCENARIO_REGISTRY)


def describe(outcome: CheckOutcome) -> str:
    """Render one failure the way the CLI does, for the assertion message."""
    where = f"[{outcome.preset}] " if outcome.preset else ""
    return f"{where}{outcome.check} — {outcome.detail}"


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_scenario_satisfies_the_contract(name: str) -> None:
    """Report every rule the scenario breaks, not just the first."""
    outcomes = check_scenario(scenario_cls=get_scenario_class(name=name))
    broken = failures(outcomes)
    assert not broken, f"{name}:\n" + "\n".join(describe(outcome) for outcome in broken)


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_scenario_is_checked_against_every_preset_it_ships(name: str) -> None:
    """A scenario with no preset cannot be launched without hand-writing knobs.

    Also guards the checks themselves: a `check_scenario` that silently returned
    nothing would make the test above pass for a scenario it never examined.
    """
    scenario_cls = get_scenario_class(name=name)
    presets = scenario_cls.knobs_preset_names()
    assert presets, "ships no knobs preset"

    checked = {outcome.preset for outcome in check_scenario(scenario_cls=scenario_cls)}
    assert set(presets) <= checked


def test_unknown_scenario_names_are_rejected() -> None:
    """The error carries the valid names, since it is usually a typo."""
    with pytest.raises(ValueError) as raised:
        get_scenario_class(name="veyroo")
    assert "veyru" in str(raised.value)


def test_a_scenario_that_names_a_judge_declares_it(
    built: tuple[str, dict[str, Any], SimulationScenario],
) -> None:
    """A judge the launch check cannot see is a run that starts and cannot score.

    The judge is built on first use, so a scenario whose knobs name one but
    whose `get_judge_models` does not report it launches happily under an
    environment holding no credential for it, spends a round, and fails inside
    the tool call. The base implementation reads the conventional knob pair, so
    this only fails for a scenario that renamed the knobs and did not override
    the hook.
    """
    name, config, scenario = built
    _ = scenario
    scenario_cls = get_scenario_class(name=name)
    fields = scenario_cls.knobs_model().model_fields
    declares_a_judge = "judge_model" in fields and "judge_provider" in fields
    reported = scenario_cls.get_judge_models(knobs=config)
    if not declares_a_judge:
        assert reported == (), f"{name} reports a judge but declares no judge knobs"
        return
    assert reported, f"{name} declares judge knobs but reports no judge model"
    assert [entry.model for entry in reported] == [config["judge_model"]]
    assert [entry.provider for entry in reported] == [config["judge_provider"]]
