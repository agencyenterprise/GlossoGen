"""Whether an external scenario's contributed classes are found at all.

Discovery is what puts a scenario's event types into the parser's discriminated
union. Miss them and nothing fails at startup: the run writes events fine and
then the JSONL will not parse back, which surfaces as a broken run rather than a
missing plug-in.

The awkward part is timing. ``glossogen.models.event`` builds that union while it
is itself mid-import, so discovery may import a scenario's ``events`` module but
not its ``scenario`` module, which imports back from it. The test that this
holds for external packages is the last one here.
"""

import logging
import sys
from importlib.metadata import EntryPoint
from typing import get_args

import pytest

from glossogen import scenario_entry_points
from glossogen import scenario_submodule_discovery as discovery
from glossogen.models.event_base import EventBase
from glossogen.scenario_loader import iter_scenario_classes
from glossogen.scenario_submodule_discovery import (
    ScenarioPackage,
    concrete_subclasses,
    import_scenario_submodules,
    scenario_packages,
)
from glossogen.server.runs.scenario_extension import collect_scenario_extensions
from tests.fakes.external_scenario.run_detail_extension import ExternalScenarioRunDetailExtension
from tests.unit.test_scenario_loader import declare_in_groups

FAKE_PACKAGE = "tests.fakes.external_scenario"


def declare(monkeypatch: pytest.MonkeyPatch, *points: EntryPoint) -> None:
    """Make the given entry points look installed."""
    declare_in_groups(
        monkeypatch,
        {scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP: list(points)},
    )


def external_entry_point() -> EntryPoint:
    """Return an entry point naming the fake external scenario."""
    return EntryPoint(
        name="external_scenario",
        value=f"{FAKE_PACKAGE}.scenario:ExternalScenario",
        group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
    )


def test_the_built_in_scenarios_are_all_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every shipped scenario package is covered, with none marked external."""
    declare(monkeypatch)

    packages = scenario_packages()

    assert packages, "no scenario packages found at all"
    assert all(not package.external for package in packages)
    assert any(package.import_path.endswith(".veyru") for package in packages)


def test_an_external_package_is_added_and_marked_external(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The package is derived from the entry point's module, not its name."""
    declare(monkeypatch, external_entry_point())

    packages = scenario_packages()
    external = [package for package in packages if package.external]

    assert [package.import_path for package in external] == [FAKE_PACKAGE]


def test_a_package_is_not_listed_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """An entry point pointing into glossogen's own tree adds nothing new."""
    declare(
        monkeypatch,
        EntryPoint(
            name="veyru",
            value="glossogen.scenarios.veyru.scenario:VeyruScenario",
            group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
        ),
    )

    paths = [package.import_path for package in scenario_packages()]

    assert paths.count("glossogen.scenarios.veyru") == 1


def test_an_external_events_module_is_imported_and_its_types_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The property the event union depends on, for a package outside glossogen.

    Asserts the ``scenario`` module stays unimported too: importing it here would
    reintroduce the cycle that discovery exists to avoid.
    """
    declare(monkeypatch, external_entry_point())
    for module in (f"{FAKE_PACKAGE}.events", f"{FAKE_PACKAGE}.scenario"):
        monkeypatch.delitem(sys.modules, module, raising=False)

    import_scenario_submodules(submodule_name="events")

    assert f"{FAKE_PACKAGE}.events" in sys.modules
    assert f"{FAKE_PACKAGE}.scenario" not in sys.modules, "discovery imported the scenario module"
    discovered = {cls.__name__ for cls in concrete_subclasses(base=EventBase)}
    assert "ExternalScenarioProbed" in discovered


def test_each_built_in_extension_is_collected_under_its_own_scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keyed by the scenario that declared it, and only scenarios that declare one.

    The key and the payload's ``scenario_name`` discriminator must agree, or the
    detail reader would build one scenario's extras and the union would validate
    them as another's.
    """
    declare(monkeypatch)

    extensions = collect_scenario_extensions()

    declaring = {
        name
        for name, scenario_cls in iter_scenario_classes()
        if scenario_cls.run_detail_extension() is not None
    }
    assert set(extensions) == declaring
    assert {"veyru", "spot_the_difference"} <= declaring, "a shipped extension went missing"
    assert "signal_game" not in extensions
    for name, extension in extensions.items():
        field = extension.extras_model_cls.model_fields["scenario_name"]
        assert get_args(field.annotation) == (name,)


def test_an_external_scenario_contributes_its_run_detail_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An external scenario's ``run_detail_extension()`` is collected like a built-in's.

    This feeds the ``scenario_extras`` discriminated union on the run-detail
    response, so an extension that is never collected leaves the scenario's own
    data missing from the API with nothing logged.
    """
    declare(monkeypatch, external_entry_point())

    extensions = collect_scenario_extensions()

    assert isinstance(extensions["external_scenario"], ExternalScenarioRunDetailExtension)
    assert "veyru" in extensions, "a built-in extension went missing"


def test_a_broken_external_events_module_is_tolerated(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One third-party plug-in must not stop glossogen reading its own event log.

    This is what ``ScenarioPackage.external`` distinguishes, and the built-in half
    is asserted below.
    """
    broken = "tests.fakes.scenario_with_broken_events"
    declare(
        monkeypatch,
        EntryPoint(
            name="broken_events",
            value=f"{broken}.scenario:Whatever",
            group=scenario_entry_points.SCENARIO_ENTRY_POINT_GROUP,
        ),
    )
    monkeypatch.delitem(sys.modules, f"{broken}.events", raising=False)

    with caplog.at_level(logging.ERROR):
        import_scenario_submodules(submodule_name="events")

    assert broken in caplog.text, "the failure is reported, not swallowed silently"


def test_a_broken_built_in_events_module_is_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half: our own broken module is a bug here and must not be hidden."""
    broken = "tests.fakes.scenario_with_broken_events"
    monkeypatch.setattr(
        target=discovery,
        name="scenario_packages",
        value=lambda: [ScenarioPackage(import_path=broken, external=False)],
    )
    monkeypatch.delitem(sys.modules, f"{broken}.events", raising=False)

    with pytest.raises(RuntimeError, match="deliberately broken"):
        import_scenario_submodules(submodule_name="events")
