"""`assert_scenario_is_registered`, the check `check-scenario` cannot make.

The command resolves a name through the loader, so a scenario whose entry point
never took effect fails there by not being found. What it cannot report is that
the name found somebody else's class, because it has no other class to compare
against. That is the case these cover.

Nothing here installs a distribution: entry points are declared through the same
stand-in the loader's own tests use.
"""

import subprocess
import sys
from importlib.metadata import EntryPoint

import pytest

from glossogen import scenario_entry_points, scenario_loader
from glossogen.scenario_registry import SCENARIO_REGISTRY
from glossogen.testing import assert_scenario_is_registered
from tests.fakes.external_scenario.scenario import ExternalScenario
from tests.fakes.installed_entry_points import declare_in_groups

EXTERNAL_MODULE = "tests.fakes.external_scenario.scenario"


class ScenarioNamedAfterABuiltIn(ExternalScenario):
    """A scenario whose author picked a name a built-in already holds."""

    @classmethod
    def name(cls) -> str:
        """Return a name the platform ships a scenario under."""
        return "veyru"


def declare(monkeypatch: pytest.MonkeyPatch, *points: EntryPoint) -> None:
    """Make the given scenario entry points look installed."""
    declare_in_groups(
        monkeypatch,
        {scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP: list(points)},
    )


@pytest.fixture(autouse=True)
def forget_previous_warnings() -> None:
    """Clear the loader's once-per-process warning cache before each test."""
    scenario_loader.forget_reported_problems()


def test_a_declared_scenario_resolving_to_itself_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The case an author expects: their entry point names their class."""
    declare(
        monkeypatch,
        EntryPoint(
            name=ExternalScenario.name(),
            value=f"{EXTERNAL_MODULE}:ExternalScenario",
            group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
        ),
    )

    assert_scenario_is_registered(scenario_cls=ExternalScenario)


def test_an_undeclared_scenario_says_to_declare_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """A package installed without its entry point resolves to nothing.

    The message names the group, because the fix is one line of `pyproject.toml`
    and a reinstall.
    """
    declare(monkeypatch)

    with pytest.raises(AssertionError) as raised:
        assert_scenario_is_registered(scenario_cls=ExternalScenario)

    assert "nothing is registered under" in str(raised.value)
    assert "glossogen.scenarios.v1" in str(raised.value)


def test_a_name_a_built_in_holds_reports_whose_class_won(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name already taken stays with the built-in, and the collision is logged.

    `check-scenario veyru` run by this author would report a healthy scenario:
    the built-in one. Identity is the only thing that separates the two, so the
    message carries both classes.
    """
    declare(
        monkeypatch,
        EntryPoint(
            name="veyru",
            value=f"{EXTERNAL_MODULE}:ExternalScenario",
            group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
        ),
    )

    with pytest.raises(AssertionError) as raised:
        assert_scenario_is_registered(scenario_cls=ScenarioNamedAfterABuiltIn)

    message = str(raised.value)
    assert SCENARIO_REGISTRY["veyru"].__qualname__ in message
    assert ScenarioNamedAfterABuiltIn.__qualname__ in message


def test_it_still_fails_under_python_dash_o() -> None:
    """`-O` strips `assert`, so a check written as one passes while testing nothing.

    That is the one failure a testing package must not have, and it cannot be
    observed from inside a suite that is not itself optimised. So this runs one.
    """
    impostor = (
        "from glossogen.scenario_loader import get_scenario_class\n"
        "from glossogen.testing import assert_scenario_is_registered\n"
        "class Impostor(get_scenario_class(name='veyru')):\n"
        "    @classmethod\n"
        "    def name(cls) -> str:\n"
        "        return 'veyru'\n"
        "assert_scenario_is_registered(scenario_cls=Impostor)\n"
    )

    result = subprocess.run(
        [sys.executable, "-O", "-c", impostor],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, "the collision went unreported under -O"
    assert "AssertionError" in result.stderr
