"""Helpers for discovering scenario-contributed classes without namespace scanning.

Scenarios register plug-in classes (event types, run-detail extensions) by
defining them in a conventionally-named submodule of their package. Discovery
is two steps: import every scenario's submodule so its classes are defined,
then read the base class's ``__subclasses__`` registry. This avoids scanning a
module's namespace with ``dir`` + ``getattr`` and the re-export false positives
that scan is prone to.

Both the scenarios shipped here and those declared by other installed
distributions are covered. Only the named submodule is imported, never the
scenario's ``scenario`` module: :mod:`glossogen.models.event` runs this while it
is itself mid-import, and a ``scenario`` module imports back from it.
"""

import importlib
import inspect
import logging
import pkgutil
from typing import NamedTuple, TypeVar

import glossogen.scenarios
from glossogen.scenario_entry_points import scenario_entry_points, scenario_package_of

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ScenarioPackage(NamedTuple):
    """A scenario's package, and whether it was contributed from outside glossogen.

    ``external`` decides what a broken submodule costs. A built-in that fails to
    import is a bug here and is raised. An external one is logged and skipped, so a
    third-party scenario cannot stop glossogen reading an event log that has nothing
    to do with it.
    """

    import_path: str
    external: bool


def scenario_packages() -> list[ScenarioPackage]:
    """Return every scenario package, built-in first, then external.

    Built-ins are the subpackages of ``glossogen.scenarios``. External ones are
    read from installed entry-point metadata, which imports nothing. A package
    already covered as a built-in is not repeated.
    """
    packages = [
        ScenarioPackage(import_path=f"glossogen.scenarios.{module_info.name}", external=False)
        for module_info in pkgutil.iter_modules(glossogen.scenarios.__path__)
        if module_info.ispkg
    ]
    known = {package.import_path for package in packages}
    for entry_point in scenario_entry_points().values():
        import_path = scenario_package_of(entry_point=entry_point)
        if import_path in known:
            continue
        known.add(import_path)
        packages.append(ScenarioPackage(import_path=import_path, external=True))
    return packages


def import_scenario_submodules(submodule_name: str) -> None:
    """Import ``<scenario_pkg>.<submodule_name>`` for every scenario package.

    The submodule is opt-in, so a package that does not define it is skipped.
    Importing a class-defining module is what registers its classes in the base
    class's ``__subclasses__``.

    A submodule that exists but raises is a different thing from one that is
    absent, and is not silently skipped: an event module dropped that way would
    surface much later as an event type missing from the parser's union.
    """
    for package in scenario_packages():
        module_path = f"{package.import_path}.{submodule_name}"
        try:
            importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            if exc.name == module_path:
                continue
            _report_broken_submodule(module_path=module_path, external=package.external)
        except Exception:
            _report_broken_submodule(module_path=module_path, external=package.external)


def _report_broken_submodule(module_path: str, external: bool) -> None:
    """Log the failure, then re-raise it unless the package came from outside.

    The bare ``raise`` re-raises the exception the caller is still handling, which
    is why this is only ever called from inside an ``except``. Returning instead
    leaves that handler to fall through, and the caller's loop moves on to the
    next package.
    """
    logger.exception("Failed to import %s", module_path)
    if not external:
        raise


def concrete_subclasses(base: type[T]) -> list[type[T]]:
    """Return every loaded concrete (non-abstract) subclass of ``base``, recursively.

    Walks the ``__subclasses__`` tree so multi-level hierarchies are covered,
    and skips abstract intermediate classes. Only subclasses whose defining
    module has been imported are visible, so callers import the relevant
    submodules first (see :func:`import_scenario_submodules`).
    """
    discovered: list[type[T]] = []
    for subclass in base.__subclasses__():
        if not inspect.isabstract(subclass):
            discovered.append(subclass)
        discovered.extend(concrete_subclasses(base=subclass))
    return discovered
