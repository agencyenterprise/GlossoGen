"""`assert_scenario_is_registered`, the check a test importing its own class cannot make.

Importing a scenario class registers it whether or not the project's configured
sources would load it, so these check the catalog the sources load instead.
"""

import subprocess
import sys

import pytest

from glossogen.scenario_contract import catalog
from glossogen.scenario_contract.catalog import (
    built_in_scenario_sources,
    current_scenario_catalog,
    load_scenario_catalog,
)
from glossogen.scenario_contract.scenario_source_kinds import ModuleSource
from glossogen.testing import assert_scenario_is_registered
from tests.fakes.external_scenario.scenario import ExternalScenario

BUILT_IN_SCENARIOS = dict(current_scenario_catalog().classes())


class ScenarioNamedAfterABuiltIn(ExternalScenario):
    """A scenario whose author picked a name a built-in already holds."""

    @classmethod
    def name(cls) -> str:
        """Return a name the platform ships a scenario under."""
        return "veyru"


@pytest.fixture(autouse=True)
def restore_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put the process catalog back after a test loads another."""
    monkeypatch.setattr(catalog, "_current", current_scenario_catalog())


def test_a_scenario_its_sources_load_passes() -> None:
    """The case an author expects: the configured source reaches their class."""
    load_scenario_catalog(
        sources=(
            *built_in_scenario_sources(),
            ModuleSource(module="tests.fakes.external_scenario", origin="test"),
        )
    )

    assert_scenario_is_registered(scenario_cls=ExternalScenario)


def test_a_scenario_its_sources_leave_out_says_where_to_add_it() -> None:
    """Importing the class registered it, but the catalog the sources load does not hold it."""
    load_scenario_catalog(sources=built_in_scenario_sources())

    with pytest.raises(AssertionError) as raised:
        assert_scenario_is_registered(scenario_cls=ExternalScenario)

    assert "do not load 'external_scenario'" in str(raised.value)
    assert "[tool.glossogen] scenarios" in str(raised.value)


def test_a_name_a_built_in_holds_reports_whose_class_won() -> None:
    """Identity is the only thing that separates the two, so the message carries both."""
    with pytest.raises(AssertionError) as raised:
        assert_scenario_is_registered(scenario_cls=ScenarioNamedAfterABuiltIn)

    message = str(raised.value)
    assert BUILT_IN_SCENARIOS["veyru"].__qualname__ in message
    assert ScenarioNamedAfterABuiltIn.__qualname__ in message


def test_it_still_fails_under_python_dash_o() -> None:
    """`-O` strips `assert`, so a check written as one passes while testing nothing.

    That is the one failure a testing package must not have, and it cannot be
    observed from inside a suite that is not itself optimised. So this runs one.
    """
    impostor = (
        "from glossogen.scenarios.veyru.scenario import VeyruScenario\n"
        "from glossogen.testing import assert_scenario_is_registered\n"
        "class Impostor(VeyruScenario):\n"
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
