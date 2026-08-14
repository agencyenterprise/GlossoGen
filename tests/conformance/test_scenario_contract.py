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
