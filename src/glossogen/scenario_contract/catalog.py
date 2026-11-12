"""The scenarios this process can run, loaded once from a list of sources.

A source says which modules to import. Importing a module runs the
``@scenario`` decorators in it (:mod:`glossogen.scenario_contract.registration`),
and the catalog keeps the classes registered from the modules its sources
imported. :func:`load_scenario_catalog` builds the catalog and makes it the
process's current one; :func:`current_scenario_catalog` answers every lookup
after that and raises :class:`ScenarioCatalogNotLoaded` before it. The current
catalog also answers which event types each scenario declares, for the run
readers in :mod:`glossogen.run_storage.event_parsing`: it installs that lookup
there whenever it becomes current.

:class:`PackageScanSource`, which scans an importable package's directory, is the
built-in scenarios' source. The kinds a user configures (a module, a file, a
directory) are in :mod:`glossogen.scenario_contract.scenario_source_kinds`, and
which of them a process loads is decided by
:mod:`glossogen.scenario_contract.scenario_sources`.
"""

import ast
import importlib
import logging
import os
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple, Protocol, Self

from pydantic import PydanticUserError

from glossogen.models.event import core_event_types, fixed_event_type, parser_for
from glossogen.models.event_base import EventBase
from glossogen.run_storage.event_parsing import (
    ScenarioCatalogNotLoaded,
    install_scenario_event_types,
)
from glossogen.scenario_contract.protocol import SimulationScenario
from glossogen.scenario_contract.registration import registered_scenarios
from glossogen.scenario_contract.scenario_name import is_valid_scenario_name

logger = logging.getLogger(__name__)

BUILT_IN_SCENARIOS_PACKAGE = "glossogen.scenarios"

_REGISTRATION_MODULE = "glossogen.scenario_contract.registration"
_REGISTRATION_PACKAGE, _, _REGISTRATION_SUBMODULE = _REGISTRATION_MODULE.rpartition(".")
_DECORATOR_NAME = "scenario"


class ScenarioCatalogError(Exception):
    """Raised when a source registers a scenario the catalog cannot accept."""


class ScenarioNotLoaded(ValueError):
    """Raised when a scenario is asked for by name and this process has not loaded it."""


class SourceImport(NamedTuple):
    """What importing one source did.

    ``module_names`` are the modules whose registered classes belong to the
    source. ``child_entries`` are the ``GLOSSOGEN_SCENARIOS`` entries that make a
    child process import the same modules without resolving anything again, as
    module names. ``child_import_roots`` are the directories those names import
    from, which a child gets on its ``PYTHONPATH``, so each module keeps the name
    and package it had in the parent.
    """

    module_names: tuple[str, ...]
    child_entries: tuple[str, ...]
    child_import_roots: tuple[str, ...]


class ScenarioSource(Protocol):
    """Somewhere scenario modules are imported from."""

    def describe(self) -> str:
        """Return the source and where it was configured, for a listing or an error."""
        ...

    def import_scenario_modules(self) -> SourceImport:
        """Import this source's scenario modules and report what was imported."""
        ...


class LoadedSource(NamedTuple):
    """One source as the catalog loaded it, and the scenarios it registered."""

    source: ScenarioSource
    scenario_names: tuple[str, ...]
    child_entries: tuple[str, ...]
    child_import_roots: tuple[str, ...]


class PackageScanSource(NamedTuple):
    """An importable package whose directory is scanned for scenario modules.

    Every ``.py`` file under the package's directory, descending only into
    subpackages, is read; a file is imported only if its syntax tree shows a class
    decorated with ``@scenario`` from
    :mod:`glossogen.scenario_contract.registration`. Scripts and helper modules
    beside a scenario are never executed by the scan.
    """

    package: str
    origin: str

    def describe(self) -> str:
        """Return the package's dotted name and where it was configured."""
        return f"{self.package} ({self.origin})"

    def import_scenario_modules(self) -> SourceImport:
        """Import the package's files that register a scenario.

        A child process loads the built-in package on its own, so this source
        hands it no entries.
        """
        return SourceImport(
            module_names=tuple(import_package_scenario_modules(package=self.package)),
            child_entries=(),
            child_import_roots=(),
        )


def import_package_scenario_modules(package: str) -> list[str]:
    """Import the files under an importable package that register a scenario.

    Returns their dotted names. Descends only into subpackages, as
    :class:`PackageScanSource` describes.
    """
    package_module = importlib.import_module(package)
    imported: list[str] = []
    for directory in getattr(package_module, "__path__", []):
        for module_name in _scenario_modules_under(
            directory=Path(directory), module_prefix=package
        ):
            importlib.import_module(module_name)
            imported.append(module_name)
    return imported


def built_in_scenario_sources() -> tuple[ScenarioSource, ...]:
    """Return the sources of the scenarios shipped with glossogen."""
    return (PackageScanSource(package=BUILT_IN_SCENARIOS_PACKAGE, origin="built-in"),)


class ScenarioCatalog:
    """The scenarios one process loaded, by name, and the sources they came from."""

    def __init__(
        self,
        scenarios: Mapping[str, type[SimulationScenario]],
        loaded_sources: tuple[LoadedSource, ...],
    ) -> None:
        """Hold ``scenarios`` loaded from ``loaded_sources``. See :func:`load_scenario_catalog`."""
        self._scenarios = MappingProxyType(dict(sorted(scenarios.items())))
        self._loaded_sources = loaded_sources

    @property
    def loaded_sources(self) -> tuple[LoadedSource, ...]:
        """Return the sources this catalog was loaded from, in load order."""
        return self._loaded_sources

    @property
    def sources(self) -> tuple[ScenarioSource, ...]:
        """Return the sources themselves, in load order, to load them again."""
        return tuple(loaded.source for loaded in self._loaded_sources)

    def child_scenario_sources(self) -> str:
        """Return the ``GLOSSOGEN_SCENARIOS`` value that makes a child load this catalog.

        Every source's child entries, joined with ``os.pathsep``. Empty when only
        the built-ins were loaded, which a child reads as "no sources beyond the
        built-ins" rather than as unset.
        """
        return os.pathsep.join(
            entry for loaded in self._loaded_sources for entry in loaded.child_entries
        )

    def child_import_roots(self) -> list[str]:
        """Return the directories a child needs on ``sys.path`` to import this catalog's modules.

        In load order, each once.
        """
        roots: list[str] = []
        for loaded in self._loaded_sources:
            for root in loaded.child_import_roots:
                if root not in roots:
                    roots.append(root)
        return roots

    def not_loaded_message(self, name: str) -> str:
        """Explain that ``name`` is not loaded, listing where this catalog came from."""
        sources = "\n".join(f"  {loaded.source.describe()}" for loaded in self._loaded_sources)
        return (
            f"Scenario {name!r} is not loaded in this process. It loaded scenarios from:\n"
            f"{sources}\n"
            f"Loaded scenarios: {', '.join(self.names())}.\n"
            "Add the scenario's module or path to [tool.glossogen] scenarios in your "
            "pyproject.toml, or pass it with --scenarios."
        )

    def names(self) -> list[str]:
        """Return every scenario name in the catalog, sorted."""
        return list(self._scenarios)

    def classes(self) -> list[tuple[str, type[SimulationScenario]]]:
        """Return every scenario as ``(name, class)``, sorted by name."""
        return list(self._scenarios.items())

    def find(self, name: str) -> type[SimulationScenario] | None:
        """Return the scenario class called ``name``, or None if the catalog has none."""
        return self._scenarios.get(name)

    def event_types_of(self, name: str) -> tuple[type[EventBase], ...] | None:
        """Return the event types scenario ``name`` declares, or None if the catalog has none."""
        scenario_cls = self._scenarios.get(name)
        if scenario_cls is None:
            return None
        return scenario_cls.event_types()

    def including(self, name: str, scenario_cls: type[SimulationScenario]) -> Self:
        """Return a copy of this catalog with ``scenario_cls`` under ``name``, replacing any."""
        return type(self)(
            scenarios={**self._scenarios, name: scenario_cls},
            loaded_sources=self._loaded_sources,
        )

    def get(self, name: str) -> type[SimulationScenario]:
        """Return the scenario class called ``name``.

        Raises :class:`ScenarioNotLoaded`, with :meth:`not_loaded_message`, if the
        catalog has none.
        """
        found = self._scenarios.get(name)
        if found is None:
            raise ScenarioNotLoaded(self.not_loaded_message(name=name))
        return found


_current: ScenarioCatalog | None = None


def load_scenario_catalog(sources: tuple[ScenarioSource, ...]) -> ScenarioCatalog:
    """Import every source, build the catalog, and make it this process's current one.

    Raises :class:`ScenarioCatalogError` for a registered class whose name is not
    a valid scenario name, or whose ``name()`` disagrees with the name it was
    registered under. A name registered by two classes has already raised while
    the second one was imported.
    """
    scenarios: dict[str, type[SimulationScenario]] = {}
    loaded_sources: list[LoadedSource] = []
    for source in sources:
        imported = source.import_scenario_modules()
        module_names = set(imported.module_names)
        from_source = {
            name: scenario_cls
            for name, scenario_cls in registered_scenarios().items()
            if scenario_cls.__module__ in module_names
        }
        scenarios.update(from_source)
        loaded_sources.append(
            LoadedSource(
                source=source,
                scenario_names=tuple(sorted(from_source)),
                child_entries=imported.child_entries,
                child_import_roots=imported.child_import_roots,
            )
        )
    for name, scenario_cls in scenarios.items():
        _check_registered_class(name=name, scenario_cls=scenario_cls)
    catalog = ScenarioCatalog(scenarios=scenarios, loaded_sources=tuple(loaded_sources))
    _install(catalog=catalog)
    logger.debug(
        "Loaded %d scenarios from %s",
        len(scenarios),
        ", ".join(source.describe() for source in sources),
    )
    return catalog


def is_scenario_catalog_loaded() -> bool:
    """Return whether this process has loaded a catalog yet."""
    return _current is not None


def current_scenario_catalog() -> ScenarioCatalog:
    """Return the catalog this process loaded.

    Raises :class:`ScenarioCatalogNotLoaded` if none has been loaded yet.
    """
    if _current is None:
        raise ScenarioCatalogNotLoaded(
            "No scenario catalog has been loaded in this process, so no scenario can "
            "be looked up yet. The glossogen CLI loads it before running a command; "
            "code that runs outside the CLI calls "
            "glossogen.scenario_contract.catalog.load_scenario_catalog first."
        )
    return _current


@contextmanager
def scenario_catalog_installed(catalog: ScenarioCatalog) -> Generator[None]:
    """Make ``catalog`` the current one for the duration of the block, then restore."""
    previous = _current
    _install(catalog=catalog)
    try:
        yield
    finally:
        _install(catalog=previous)


def _install(catalog: ScenarioCatalog | None) -> None:
    """Make ``catalog`` the process's current catalog, and the run readers' event-type lookup."""
    global _current
    _current = catalog
    if catalog is None:
        install_scenario_event_types(lookup=None)
        return
    install_scenario_event_types(lookup=catalog.event_types_of)


def _check_registered_class(name: str, scenario_cls: type[SimulationScenario]) -> None:
    """Refuse a registered class the platform could not run under its name."""
    where = f"{scenario_cls.__module__}.{scenario_cls.__qualname__}"
    if not is_valid_scenario_name(name=name):
        raise ScenarioCatalogError(
            f"Scenario {name!r} ({where}) has an invalid name. Scenario names must "
            "start with a lowercase letter and contain only lowercase letters, "
            "digits, and underscores."
        )
    reported = scenario_cls.name()
    if reported != name:
        raise ScenarioCatalogError(
            f"Scenario {name!r} ({where}) answers name() with {reported!r}. Run "
            "directories are named after name(), and every later command looks a run "
            "up by the name it was registered under; remove the name() override."
        )
    _check_declared_event_types(where=where, event_types=scenario_cls.event_types())


def _check_declared_event_types(where: str, event_types: tuple[type[EventBase], ...]) -> None:
    """Refuse event types a run's parser could not dispatch alongside the platform's.

    Each needs a fixed ``event_type`` that no platform event and no other of the
    scenario's own events uses. Building the parser the scenario's runs are read
    with is the last check: pydantic refuses a union it cannot dispatch.
    """
    taken = {fixed_event_type(event_cls=cls): cls.__name__ for cls in core_event_types()}
    for event_cls in event_types:
        discriminator = fixed_event_type(event_cls=event_cls)
        if discriminator is None:
            raise ScenarioCatalogError(
                f"{where} declares {event_cls.__name__}, which has no fixed event_type; "
                'declare it as Literal["..."] with that value as its default'
            )
        if discriminator in taken:
            raise ScenarioCatalogError(
                f"{where} declares {event_cls.__name__} with event_type {discriminator!r}, "
                f"which {taken[discriminator]} already uses"
            )
        taken[discriminator] = event_cls.__name__
    try:
        parser_for(event_types=(*core_event_types(), *event_types))
    except PydanticUserError as exc:
        logger.exception("The parser for %s's runs could not be built", where)
        raise ScenarioCatalogError(
            f"{where}'s runs cannot be parsed with the event types it declares: {exc}"
        ) from exc


def _scenario_modules_under(directory: Path, module_prefix: str) -> list[str]:
    """Return the dotted names of the files under ``directory`` that register a scenario.

    Descends only into subpackages (directories holding ``__init__.py``) whose
    names do not start with ``.`` or ``_``, since a module elsewhere has no dotted
    name to import it by.
    """
    found: list[str] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_dir():
            if entry.name.startswith((".", "_")) or not (entry / "__init__.py").is_file():
                continue
            found.extend(
                _scenario_modules_under(
                    directory=entry, module_prefix=f"{module_prefix}.{entry.name}"
                )
            )
            continue
        if entry.suffix != ".py":
            continue
        if not uses_scenario_decorator(source=entry.read_bytes(), origin=str(entry)):
            continue
        if entry.stem == "__init__":
            found.append(module_prefix)
        else:
            found.append(f"{module_prefix}.{entry.stem}")
    return found


def uses_scenario_decorator(source: bytes, origin: str) -> bool:
    """Return whether a module's source decorates a top-level class with ``@scenario``.

    Read from the syntax tree, without importing. The decorator counts when it is
    imported from :mod:`glossogen.scenario_contract.registration`, under any alias,
    or reached as an attribute of that module. Files that do not mention the
    module are rejected before parsing. A file that does not parse is logged with
    ``origin``, the path it was read from, and treated as registering nothing.
    """
    if _REGISTRATION_SUBMODULE.encode() not in source:
        return False
    try:
        tree = ast.parse(source)
    except SyntaxError:
        logger.exception("Skipping %s: it mentions @scenario but does not parse", origin)
        return False
    decorator_names, module_names = _decorator_bindings(tree=tree)
    return any(
        _is_scenario_decorator(
            decorator=decorator, decorator_names=decorator_names, module_names=module_names
        )
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        for decorator in node.decorator_list
    )


class _DecoratorBindings(NamedTuple):
    """The local names a module binds the decorator and its module to."""

    decorator_names: frozenset[str]
    module_names: frozenset[str]


def _decorator_bindings(tree: ast.Module) -> _DecoratorBindings:
    """Read the top-level imports that bind ``scenario`` or its module to a local name."""
    decorator_names: set[str] = set()
    module_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                local = alias.asname or alias.name
                if node.module == _REGISTRATION_MODULE and alias.name == _DECORATOR_NAME:
                    decorator_names.add(local)
                if node.module == _REGISTRATION_PACKAGE and alias.name == _REGISTRATION_SUBMODULE:
                    module_names.add(local)
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _REGISTRATION_MODULE:
                    module_names.add(alias.asname or alias.name)
    return _DecoratorBindings(
        decorator_names=frozenset(decorator_names), module_names=frozenset(module_names)
    )


def _is_scenario_decorator(
    decorator: ast.expr, decorator_names: frozenset[str], module_names: frozenset[str]
) -> bool:
    """Return whether one decorator expression is a call to ``scenario(...)``."""
    if not isinstance(decorator, ast.Call):
        return False
    target = decorator.func
    if isinstance(target, ast.Name):
        return target.id in decorator_names
    if isinstance(target, ast.Attribute) and target.attr == _DECORATOR_NAME:
        return ast.unparse(target.value) in module_names
    return False
