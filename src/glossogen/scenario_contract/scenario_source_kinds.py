"""The scenario sources a user configures: a module, a ``.py`` file, or a directory.

Each kind satisfies :class:`~glossogen.scenario_contract.catalog.ScenarioSource`.
A file or a directory is imported by module name relative to an import root,
which goes on ``sys.path`` the way pytest's ``pythonpath`` setting works:
``experiments/reactor.py`` under the root becomes ``experiments.reactor``, so
relative imports inside the user's package work. The root is the project
directory when the path is inside it, and the path's parent otherwise.

A directory is walked rather than imported. Only files whose syntax tree shows a
class decorated with ``@scenario`` are imported, so scripts, notebooks and
helpers beside a scenario never run. The walk does not descend into the
directories :func:`skipped_directory_reason` names; the runs directories and any
run directory among them are skipped because bundle import and pulling runs from
prod extract arbitrary files into run directories, and those must never become a
place code is imported from.
"""

import importlib
import keyword
import logging
import os
import sys
from pathlib import Path
from typing import NamedTuple

from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.scenario_contract.catalog import (
    ScenarioCatalogError,
    SourceImport,
    import_package_scenario_modules,
    uses_scenario_decorator,
)

logger = logging.getLogger(__name__)

# Directory names a walk never descends into, besides hidden and ``_``-prefixed
# ones. ``build`` and ``dist`` hold copies of the project's own modules after a
# wheel build, which would register every scenario a second time.
SKIPPED_DIRECTORY_NAMES = frozenset(
    {
        "venv",
        ".venv",
        "env",
        "node_modules",
        "site-packages",
        "__pycache__",
        "tests",
        "build",
        "dist",
    }
)

# A walk reading more ``.py`` files than this logs a warning: it is probably
# walking far more than the project, such as a home directory.
LARGE_SCAN_FILE_COUNT = 3000


class ModuleSource(NamedTuple):
    """A module given by its dotted name, imported with ``importlib``.

    A module that is a package also has its directory scanned the way the
    built-in package is, so naming an installed scenario pack is enough.
    """

    module: str
    origin: str

    def describe(self) -> str:
        """Return the module name and where it was configured."""
        return f"{self.module} ({self.origin})"

    def import_scenario_modules(self) -> SourceImport:
        """Import the module, and the scenario files of its package if it is one."""
        try:
            imported = [self.module, *import_package_scenario_modules(package=self.module)]
        except Exception as exc:
            raise ScenarioCatalogError(
                f"Scenario source {self.describe()} failed to import: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return SourceImport(
            module_names=tuple(imported), child_entries=(self.module,), child_import_roots=()
        )


class FileSource(NamedTuple):
    """One ``.py`` file, imported whether or not it uses ``@scenario``."""

    path: Path
    import_root: Path
    spec: str
    origin: str

    def describe(self) -> str:
        """Return the path as it was written and where it was configured."""
        return f"{self.spec} ({self.origin})"

    def import_scenario_modules(self) -> SourceImport:
        """Import the file by its module name under the import root."""
        module_name = import_file(path=self.path, import_root=self.import_root, source=self)
        return SourceImport(
            module_names=(module_name,),
            child_entries=(module_name,),
            child_import_roots=(str(self.import_root),),
        )


class DirectorySource(NamedTuple):
    """A directory walked for files that register a scenario.

    ``skipped_paths`` are directories never descended into, given as resolved
    paths: the installed glossogen package and the runs directories.
    """

    path: Path
    import_root: Path
    skipped_paths: frozenset[Path]
    spec: str
    origin: str

    def describe(self) -> str:
        """Return the path as it was written and where it was configured."""
        return f"{self.spec} ({self.origin})"

    def import_scenario_modules(self) -> SourceImport:
        """Import every file under the directory that registers a scenario.

        A child process gets the modules by name, with the import root on its
        path, so it imports the same ones under the same names without walking
        the directory again.
        """
        walk = _ScanWalk(skipped_paths=self.skipped_paths)
        walk.visit(directory=self.path)
        if walk.files_read > LARGE_SCAN_FILE_COUNT:
            logger.warning(
                "Scanning %s for scenarios read %d .py files. Set [tool.glossogen] "
                "scenarios in the project's pyproject.toml to name where scenarios "
                "live, or scenarios = [] to turn the scan off.",
                self.path,
                walk.files_read,
            )
        module_names = tuple(
            import_file(path=path, import_root=self.import_root, source=self) for path in walk.found
        )
        if walk.found:
            logger.info(
                "Registered scenarios from %s: %s",
                self.describe(),
                ", ".join(str(path) for path in walk.found),
            )
        child_import_roots: tuple[str, ...] = ()
        if module_names:
            child_import_roots = (str(self.import_root),)
        return SourceImport(
            module_names=module_names,
            child_entries=module_names,
            child_import_roots=child_import_roots,
        )


def skipped_directory_reason(directory: Path, skipped_paths: frozenset[Path]) -> str | None:
    """Return why a walk does not descend into ``directory``, or None if it does.

    ``directory`` is resolved. A run directory is recognised by its event log,
    ``<scenario>.jsonl`` named after its parent, so one outside the configured
    runs directories is skipped as well.
    """
    name = directory.name
    if name.startswith((".", "_")):
        return "hidden or private"
    if name in SKIPPED_DIRECTORY_NAMES:
        return "excluded by name"
    if directory in skipped_paths:
        return "the runs directory or the glossogen package"
    if event_log_path(run_dir=directory, scenario_name=directory.parent.name).is_file():
        return "a run directory"
    return None


class _ScanWalk:
    """One walk of a directory tree, collecting the files that register a scenario."""

    def __init__(self, skipped_paths: frozenset[Path]) -> None:
        self._skipped_paths = skipped_paths
        self.found: list[Path] = []
        self.files_read = 0

    def visit(self, directory: Path) -> None:
        """Walk ``directory``, unless it is one a walk skips."""
        resolved = directory.resolve()
        reason = skipped_directory_reason(directory=resolved, skipped_paths=self._skipped_paths)
        if reason is not None:
            logger.debug("Not scanning %s for scenarios: %s", resolved, reason)
            return
        try:
            entries = sorted(os.scandir(resolved), key=lambda entry: entry.name)
        except OSError:
            logger.exception("Could not list %s while scanning for scenarios", resolved)
            return
        for entry in entries:
            path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                if is_module_name_part(part=entry.name):
                    self.visit(directory=path)
                continue
            if not entry.name.endswith(".py") or not entry.is_file(follow_symlinks=False):
                continue
            if not is_module_name_part(part=path.stem):
                continue
            self.files_read += 1
            if uses_scenario_decorator(source=path.read_bytes(), origin=str(path)):
                self.found.append(path)


def is_module_name_part(part: str) -> bool:
    """Return whether ``part`` can be one component of a dotted module name."""
    return part.isidentifier() and not keyword.iskeyword(part)


def module_name_for(path: Path, import_root: Path) -> str:
    """Return the dotted name ``path`` is imported as under ``import_root``.

    ``pkg/__init__.py`` is imported as ``pkg``. Raises
    :class:`ScenarioCatalogError` when the path is outside the root or a
    component cannot be part of a module name.
    """
    try:
        relative = path.relative_to(import_root)
    except ValueError as exc:
        raise ScenarioCatalogError(f"{path} is not under {import_root}") from exc
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    if not parts or not all(is_module_name_part(part=part) for part in parts):
        raise ScenarioCatalogError(
            f"{path} cannot be imported by module name from {import_root}: every "
            "directory and the file name must be a Python identifier. Rename it, or "
            "point the source at a directory closer to the file."
        )
    return ".".join(parts)


def import_file(path: Path, import_root: Path, source: FileSource | DirectorySource) -> str:
    """Import ``path`` by its module name under ``import_root``, and return the name.

    The root goes on ``sys.path`` and stays there, so modules the file imports
    later resolve the same way. Raises :class:`ScenarioCatalogError` when the
    import fails, or when the name resolves to a different file, which happens
    when another module of the same top-level name is already importable.
    """
    module_name = module_name_for(path=path, import_root=import_root)
    root_entry = str(import_root)
    if root_entry not in sys.path:
        sys.path.insert(0, root_entry)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise ScenarioCatalogError(
            f"{path}, from scenario source {source.describe()}, failed to import as "
            f"{module_name}: {type(exc).__name__}: {exc}"
        ) from exc
    loaded_from = getattr(module, "__file__", None)
    if loaded_from is None or Path(loaded_from).resolve() != path.resolve():
        raise ScenarioCatalogError(
            f"{path}, from scenario source {source.describe()}, is imported as "
            f"{module_name}, but that name resolves to {loaded_from}. Another module "
            f"named {module_name.split('.')[0]!r} is importable here; rename the folder."
        )
    return module_name
