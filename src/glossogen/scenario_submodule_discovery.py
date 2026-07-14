"""Helpers for discovering scenario-contributed classes without namespace scanning.

Scenarios register plug-in classes (event types, run-detail extensions) by
defining them in a conventionally-named submodule of their package. Discovery
is two steps: import every scenario's submodule so its classes are defined,
then read the base class's ``__subclasses__`` registry. This avoids scanning a
module's namespace with ``dir`` + ``getattr`` and the re-export false positives
that scan is prone to.
"""

import importlib
import inspect
import pkgutil
from typing import TypeVar

import glossogen.scenarios

T = TypeVar("T")


def import_scenario_submodules(submodule_name: str) -> None:
    """Import ``<scenario_pkg>.<submodule_name>`` for every scenario package.

    Iterates the ``glossogen.scenarios`` namespace package and imports the
    named submodule from each scenario package, skipping packages that do not
    define it (the submodule is opt-in). Importing a class-defining module is
    what registers its classes in the base class's ``__subclasses__``.
    """
    for module_info in pkgutil.iter_modules(glossogen.scenarios.__path__):
        if not module_info.ispkg:
            continue
        try:
            importlib.import_module(f"glossogen.scenarios.{module_info.name}.{submodule_name}")
        except ModuleNotFoundError:
            continue


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
