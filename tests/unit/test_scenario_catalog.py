"""The ``@scenario`` decorator, the directory scan and the scenario catalog."""

import importlib
import inspect
import sys
import textwrap
from importlib.metadata import EntryPoint
from importlib.resources.abc import Traversable
from pathlib import Path

import pytest

import glossogen.scenarios
from glossogen.models.event_base import EventBase
from glossogen.scenario_contract import catalog, registration
from glossogen.scenario_contract.catalog import (
    PackageScanSource,
    ScenarioCatalogError,
    ScenarioCatalogNotLoaded,
    current_scenario_catalog,
    load_scenario_catalog,
    uses_scenario_decorator,
)
from glossogen.scenario_contract.entry_points import SCENARIO_ENTRY_POINT_GROUP
from glossogen.scenario_contract.loader import (
    available_scenario_names,
    check_entry_point_declaration,
    get_scenario_class,
)
from glossogen.scenario_contract.registration import ScenarioNameTaken, scenario
from glossogen.scenarios.veyru.scenario import VeyruScenario

BUILT_IN_PACKAGES = sorted(
    path.name
    for path in Path(glossogen.scenarios.__file__).parent.iterdir()
    if (path / "scenario.py").is_file()
)


@pytest.fixture
def empty_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the test a registry of its own, and restore the process catalog afterwards."""
    monkeypatch.setattr(registration, "_REGISTERED", {})
    monkeypatch.setattr(catalog, "_current", current_scenario_catalog())


def test_the_catalog_holds_every_built_in_under_its_package_name() -> None:
    """Run directories and recorded runs name a built-in by its package directory."""
    loaded = current_scenario_catalog()

    assert loaded.names() == BUILT_IN_PACKAGES
    for name, scenario_cls in loaded.classes():
        assert scenario_cls.name() == name
        assert scenario_cls.__module__ == f"glossogen.scenarios.{name}.scenario"


@pytest.mark.parametrize("name", BUILT_IN_PACKAGES)
def test_event_types_are_exactly_what_the_events_module_defines(name: str) -> None:
    """``event_types()`` matches the classes the ``events`` module discovery reads.

    Once parsing relies on ``event_types()`` alone, an event class left out here
    would stop parsing back from every log that holds one.
    """
    events_module = importlib.import_module(f"glossogen.scenarios.{name}.events")
    defined = {
        attribute
        for attribute in vars(events_module).values()
        if isinstance(attribute, type)
        and issubclass(attribute, EventBase)
        and attribute is not EventBase
        and attribute.__module__ == events_module.__name__
        and not inspect.isabstract(attribute)
    }
    declared = get_scenario_class(name=name).event_types()

    assert len(declared) == len(set(declared)), "an event type is declared twice"
    assert set(declared) == defined


@pytest.mark.usefixtures("empty_registry")
def test_the_decorator_sets_the_name() -> None:
    """``name()`` answers with the registered name, not the package directory."""

    @scenario(name="renamed_veyru")
    class Renamed(VeyruScenario):
        """A built-in under another name."""

    assert Renamed.name() == "renamed_veyru"
    assert registration.registered_scenarios()["renamed_veyru"] is Renamed


@pytest.mark.usefixtures("empty_registry")
def test_a_name_registered_by_two_classes_raises_naming_both_modules() -> None:
    """The second registration fails, and says where the first one came from."""

    @scenario(name="twice")
    class First(VeyruScenario):
        """The first holder of the name."""

    with pytest.raises(ScenarioNameTaken) as raised:

        @scenario(name="twice")
        class Second(VeyruScenario):
            """A different class claiming the same name."""

        _ = Second

    assert First.__module__ in str(raised.value)
    assert "First" in str(raised.value)
    assert "Second" in str(raised.value)


@pytest.mark.usefixtures("empty_registry")
def test_a_module_imported_twice_does_not_collide_with_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-importing a scenario module defines the class again, and that is not a collision."""
    write_package(
        root=tmp_path,
        package="reimported_pkg",
        files={"scen.py": decorated_scenario_module(name="reimported")},
    )
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])

    module = importlib.import_module("reimported_pkg.scen")
    importlib.reload(module)

    assert registration.registered_scenarios()["reimported"] is module.Scenario


def test_a_lookup_before_the_catalog_is_loaded_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ordering bug fails at the first lookup rather than finding no scenarios."""
    monkeypatch.setattr(catalog, "_current", None)

    with pytest.raises(ScenarioCatalogNotLoaded, match="No scenario catalog has been loaded"):
        get_scenario_class(name="veyru")
    with pytest.raises(ScenarioCatalogNotLoaded):
        available_scenario_names()


@pytest.mark.usefixtures("empty_registry")
def test_the_scan_imports_only_files_that_register_a_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scripts and helpers beside a scenario are never executed by the scan.

    The helper mentions the registration module in a comment, so it gets past the
    text check and is turned away by the syntax tree. A decorated file in a
    directory that is not a subpackage has no dotted name and is skipped.
    """
    write_package(
        root=tmp_path,
        package="scanned_pkg",
        files={
            "scen.py": decorated_scenario_module(name="scanned"),
            "helper.py": (
                "# uses glossogen.scenario_contract.registration elsewhere\n"
                "raise RuntimeError('the scan imported a helper')\n"
            ),
            "scripts/run_it.py": decorated_scenario_module(name="from_a_script"),
            "nested/__init__.py": "",
            "nested/deeper.py": decorated_scenario_module(name="nested_one"),
        },
    )
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])

    loaded = load_scenario_catalog(sources=(PackageScanSource(package="scanned_pkg"),))

    assert loaded.names() == ["nested_one", "scanned"]
    assert current_scenario_catalog() is loaded


@pytest.mark.usefixtures("empty_registry")
def test_the_catalog_keeps_only_classes_its_sources_imported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A class registered by some other import is not in a catalog that did not load it."""
    write_package(
        root=tmp_path,
        package="kept_pkg",
        files={"scen.py": decorated_scenario_module(name="kept")},
    )
    write_package(
        root=tmp_path,
        package="other_pkg",
        files={"scen.py": decorated_scenario_module(name="elsewhere")},
    )
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    importlib.import_module("other_pkg.scen")

    loaded = load_scenario_catalog(sources=(PackageScanSource(package="kept_pkg"),))

    assert loaded.names() == ["kept"]


@pytest.mark.usefixtures("empty_registry")
def test_the_catalog_refuses_an_invalid_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A name that cannot be a run-directory component is refused when the catalog loads."""
    write_package(
        root=tmp_path,
        package="invalid_pkg",
        files={"scen.py": decorated_scenario_module(name="Not-Valid")},
    )
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])

    with pytest.raises(ScenarioCatalogError, match="invalid name"):
        load_scenario_catalog(sources=(PackageScanSource(package="invalid_pkg"),))


@pytest.mark.parametrize(
    "source",
    [
        """
        from glossogen.scenario_contract.registration import scenario

        @scenario(name="x")
        class X: ...
        """,
        """
        from glossogen.scenario_contract.registration import scenario as register

        @register(name="x")
        class X: ...
        """,
        """
        from glossogen.scenario_contract import registration

        @registration.scenario(name="x")
        class X: ...
        """,
        """
        import glossogen.scenario_contract.registration

        @glossogen.scenario_contract.registration.scenario(name="x")
        class X: ...
        """,
    ],
)
def test_the_decorator_is_recognised_however_it_is_imported(source: str) -> None:
    """Each import form an author might write counts."""
    assert uses_scenario_decorator(source=textwrap.dedent(source).encode(), origin="x.py")


@pytest.mark.parametrize(
    "source",
    [
        """
        # glossogen.scenario_contract.registration is mentioned only here
        class X: ...
        """,
        """
        from glossogen.scenario_contract.registration import scenario

        class X: ...
        """,
        """
        from somewhere_else import scenario

        # glossogen.scenario_contract.registration
        @scenario(name="x")
        class X: ...
        """,
        """
        from glossogen.scenario_contract.registration import scenario

        @scenario(name="x")
        def not_a_class(): ...
        """,
        """
        from glossogen.scenario_contract.registration import scenario
        def broken(:
        """,
    ],
)
def test_files_that_do_not_register_a_scenario_are_not_recognised(source: str) -> None:
    """A mention, an unused import, another ``scenario`` or a broken file is not registration."""
    assert not uses_scenario_decorator(source=textwrap.dedent(source).encode(), origin="x.py")


def test_a_file_that_does_not_parse_is_logged_by_path(caplog: pytest.LogCaptureFixture) -> None:
    """A broken scenario module is named in the log, not silently left unregistered."""
    source = b"from glossogen.scenario_contract.registration import scenario\ndef broken(:\n"

    assert not uses_scenario_decorator(source=source, origin="pkg/broken.py")
    assert "pkg/broken.py" in caplog.text


def test_an_undecorated_subclass_of_a_built_in_answers_with_its_own_package() -> None:
    """An entry-point scenario subclassing a built-in keeps the name its package gives it.

    The registered name is not inherited, so the entry-point declaration check
    compares against the subclass's own package, as it did before registration.
    """

    class FromAnotherPackage(VeyruScenario):
        """Stands in for an installed scenario built on Veyru."""

        @classmethod
        def scenario_package_files(cls) -> Traversable:
            return Path("custom_pkg")

    assert FromAnotherPackage.name() == "custom_pkg"
    check_entry_point_declaration(
        name="custom_pkg",
        entry_point=EntryPoint(
            name="custom_pkg",
            value="custom_pkg.scenario:FromAnotherPackage",
            group=SCENARIO_ENTRY_POINT_GROUP,
        ),
        loaded=FromAnotherPackage,
    )


def decorated_scenario_module(name: str) -> str:
    """Return a module defining a scenario registered as ``name``."""
    return textwrap.dedent(f"""
        from glossogen.scenario_contract.registration import scenario
        from glossogen.scenarios.veyru.scenario import VeyruScenario


        @scenario(name={name!r})
        class Scenario(VeyruScenario):
            pass
        """)


def write_package(root: Path, package: str, files: dict[str, str]) -> None:
    """Write a package named ``package`` under ``root`` holding ``files``."""
    package_dir = root / package
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("")
    for relative, content in files.items():
        path = package_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
