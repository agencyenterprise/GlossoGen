"""The scenario sources a user configures: a module, a ``.py`` file, or a directory.

Each kind satisfies :class:`~glossogen.scenario_contract.catalog.ScenarioSource`.
A file or a directory is imported by module name relative to an import root,
which goes on ``sys.path`` the way pytest's ``pythonpath`` setting works:
``experiments/reactor.py`` under the root becomes ``experiments.reactor``, so
relative imports inside the user's package work. The root is the project
directory when the path is inside it, and the path's parent otherwise.

A directory is walked rather than imported. Only files whose syntax tree shows a
class decorated with ``@scenario`` are imported, so scripts, notebooks and
helpers beside a scenario never run. Below the directory it starts at, the walk
does not descend into the directories :func:`skipped_directory_reason` names; the
runs directories and any run directory among them are skipped, the starting
directory included, because bundle import and pulling runs from prod extract
arbitrary files into run directories, and those must never become a place code
is imported from. The walk stops after :data:`LARGE_SCAN_FILE_COUNT` ``.py``
files.

The default scan of the project directory is the one source that is not strict:
a file it finds that fails to import is logged and left out, so one broken draft
under the project does not stop every command.
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
    SINGLE_MODULE_ENTRY_SUFFIX,
    ScenarioCatalogError,
    SourceImport,
    import_package_scenario_modules,
    uses_scenario_decorator,
)
from glossogen.scenario_contract.registration import (
    registrations_snapshot,
    restore_registrations,
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

# A walk stops after reading this many ``.py`` files: it is probably walking far
# more than the project, such as a home directory.
LARGE_SCAN_FILE_COUNT = 3000

# How far below a folder whose name is not an identifier the walk looks for a
# decorated file, to say why that file was not loaded.
_UNIMPORTABLE_FOLDER_LOOKAHEAD = 2


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
            logger.exception("Scenario source %s failed to import", self.describe())
            raise ScenarioCatalogError(
                f"Scenario source {self.describe()} failed to import: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return SourceImport(
            module_names=tuple(imported),
            child_entries=(self.module,),
            child_import_roots=(),
            strict=True,
        )


class SingleModuleSource(NamedTuple):
    """One module imported on its own, even when it is a package.

    Written ``<module>.__init__`` in ``GLOSSOGEN_SCENARIOS``. A parent process
    hands a child this form for a package ``__init__.py`` its walk imported, so
    the child imports that file and not the rest of the package, which the
    parent's walk may have skipped.
    """

    module: str
    origin: str

    def describe(self) -> str:
        """Return the module name and where it was configured."""
        return f"{self.module}{SINGLE_MODULE_ENTRY_SUFFIX} ({self.origin})"

    def import_scenario_modules(self) -> SourceImport:
        """Import the module alone."""
        try:
            importlib.import_module(self.module)
        except Exception as exc:
            logger.exception("Scenario source %s failed to import", self.describe())
            raise ScenarioCatalogError(
                f"Scenario source {self.describe()} failed to import: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        return SourceImport(
            module_names=(self.module,),
            child_entries=(f"{self.module}{SINGLE_MODULE_ENTRY_SUFFIX}",),
            child_import_roots=(),
            strict=True,
        )


class FileSource(NamedTuple):
    """One ``.py`` file, imported whether or not it uses ``@scenario``.

    ``inside_project`` says whether the file is under the project root, which
    is then its import root.
    """

    path: Path
    import_root: Path
    inside_project: bool
    spec: str
    origin: str

    def describe(self) -> str:
        """Return the path as it was written and where it was configured."""
        return f"{self.spec} ({self.origin})"

    def import_scenario_modules(self) -> SourceImport:
        """Import the file by its module name under the import root."""
        module_name = module_name_for(
            path=self.path,
            import_root=self.import_root,
            advice=_rename_advice(inside_project=self.inside_project, is_directory=False),
        )
        import_file(
            path=self.path, module_name=module_name, import_root=self.import_root, source=self
        )
        return SourceImport(
            module_names=(module_name,),
            child_entries=(child_entry_for(path=self.path, module_name=module_name),),
            child_import_roots=(str(self.import_root),),
            strict=True,
        )


class DirectorySource(NamedTuple):
    """A directory walked for files that register a scenario.

    ``skipped_paths`` are directories never descended into, given as resolved
    paths: the installed glossogen package and the runs directories.
    ``inside_project`` says whether the directory is under the project root,
    which is then its import root. ``is_project_scan`` marks the scan made when
    no source is configured, the one source that is not strict.
    """

    path: Path
    import_root: Path
    skipped_paths: frozenset[Path]
    inside_project: bool
    is_project_scan: bool
    spec: str
    origin: str

    def describe(self) -> str:
        """Return the path as it was written and where it was configured."""
        return f"{self.spec} ({self.origin})"

    def import_scenario_modules(self) -> SourceImport:
        """Import every file under the directory that registers a scenario.

        A child process gets the modules by name, with the import root on its
        path, so it imports the same ones under the same names without walking
        the directory again. In the project scan, a file that fails to import is
        logged and left out; any other directory source raises.
        """
        walk = _ScanWalk(root=self.path, skipped_paths=self.skipped_paths)
        walk.visit_root()
        advice = _rename_advice(inside_project=self.inside_project, is_directory=True)
        newly_imported: list[Path] = []
        module_names: list[str] = []
        child_entries: list[str] = []
        for path in walk.found:
            modules_before = set(sys.modules)
            if self.is_project_scan:
                scanned_name = _import_scanned_file(
                    path=path, import_root=self.import_root, advice=advice, source=self
                )
                if scanned_name is None:
                    continue
                module_name = scanned_name
            else:
                module_name = module_name_for(
                    path=path, import_root=self.import_root, advice=advice
                )
                import_file(
                    path=path, module_name=module_name, import_root=self.import_root, source=self
                )
            if module_name not in modules_before:
                newly_imported.append(path)
            module_names.append(module_name)
            child_entries.append(child_entry_for(path=path, module_name=module_name))
        # A catalog loaded again, as `validate <path>` does to add its source,
        # imports the same files a second time; only a first import is news.
        if newly_imported:
            logger.info(
                "Registered scenarios from %s: %s",
                self.describe(),
                ", ".join(str(path) for path in newly_imported),
            )
        child_import_roots: tuple[str, ...] = ()
        if module_names:
            child_import_roots = (str(self.import_root),)
        return SourceImport(
            module_names=tuple(module_names),
            child_entries=tuple(child_entries),
            child_import_roots=child_import_roots,
            strict=not self.is_project_scan,
        )


def child_entry_for(path: Path, module_name: str) -> str:
    """Return the ``GLOSSOGEN_SCENARIOS`` entry that makes a child import exactly ``path``.

    A package's ``__init__.py`` gets the single-module form, so the child does
    not scan the rest of the package.
    """
    if path.name == "__init__.py":
        return f"{module_name}{SINGLE_MODULE_ENTRY_SUFFIX}"
    return module_name


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
    return protected_directory_reason(directory=directory, skipped_paths=skipped_paths)


def protected_directory_reason(directory: Path, skipped_paths: frozenset[Path]) -> str | None:
    """Return why no walk reads ``directory``, even one that starts there, or None.

    These are the runs directories, the installed glossogen package and run
    directories: places nothing is imported from whatever the source names.
    """
    if directory in skipped_paths:
        return "the runs directory or the glossogen package"
    if event_log_path(run_dir=directory, scenario_name=directory.parent.name).is_file():
        return "a run directory"
    return None


class _ScanWalk:
    """One walk of a directory tree, collecting the files that register a scenario."""

    def __init__(self, root: Path, skipped_paths: frozenset[Path]) -> None:
        self._root = root
        self._skipped_paths = skipped_paths
        self.found: list[Path] = []
        self.files_read = 0
        self.stopped = False

    def visit_root(self) -> None:
        """Walk the root, which only the protected-directory rules can rule out."""
        resolved = self._root.resolve()
        reason = protected_directory_reason(directory=resolved, skipped_paths=self._skipped_paths)
        if reason is not None:
            logger.warning("Not scanning %s for scenarios: it is %s", resolved, reason)
            return
        self._visit_entries(directory=resolved)

    def _visit(self, directory: Path) -> None:
        """Walk ``directory``, unless it is one a walk skips."""
        resolved = directory.resolve()
        reason = skipped_directory_reason(directory=resolved, skipped_paths=self._skipped_paths)
        if reason is not None:
            logger.debug("Not scanning %s for scenarios: %s", resolved, reason)
            return
        self._visit_entries(directory=resolved)

    def _visit_entries(self, directory: Path) -> None:
        """Read the ``.py`` files directly in ``directory`` and walk its subdirectories."""
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            logger.exception("Could not list %s while scanning for scenarios", directory)
            return
        for entry in entries:
            if self.stopped:
                return
            path = Path(entry.path)
            if entry.is_dir(follow_symlinks=False):
                if is_module_name_part(part=entry.name):
                    self._visit(directory=path)
                else:
                    self._note_unimportable_folder(directory=path)
                continue
            if not entry.name.endswith(".py") or not entry.is_file(follow_symlinks=False):
                continue
            if not is_module_name_part(part=path.stem):
                continue
            if self._read_counts_as_decorated(path=path):
                self.found.append(path)

    def _read_counts_as_decorated(self, path: Path) -> bool:
        """Read one ``.py`` file against the walk's limit; return whether it uses ``@scenario``.

        Stops the walk instead of reading once the limit is reached.
        """
        if self.files_read >= LARGE_SCAN_FILE_COUNT:
            self._stop()
            return False
        self.files_read += 1
        return uses_scenario_decorator(source=path.read_bytes(), origin=str(path))

    def _decorated_file_within(self, directory: Path, depth: int) -> Path | None:
        """Return the first file using ``@scenario`` within ``depth`` levels of ``directory``."""
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError:
            logger.exception("Could not list %s while scanning for scenarios", directory)
            return None
        for entry in entries:
            if self.stopped:
                return None
            path = Path(entry.path)
            if not entry.name.endswith(".py") or not entry.is_file(follow_symlinks=False):
                continue
            if self._read_counts_as_decorated(path=path):
                return path
        if depth <= 1:
            return None
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False) or entry.name.startswith((".", "_")):
                continue
            if entry.name in SKIPPED_DIRECTORY_NAMES:
                continue
            found = self._decorated_file_within(directory=Path(entry.path), depth=depth - 1)
            if found is not None:
                return found
        return None

    def _stop(self) -> None:
        """Stop the walk at the file limit, and say so once."""
        if self.stopped:
            return
        self.stopped = True
        logger.warning(
            "Stopped scanning %s for scenarios after reading %d .py files; scenarios in "
            "the files not read yet are not loaded. Set [tool.glossogen] scenarios in "
            "the project's pyproject.toml to name where scenarios live, or "
            "scenarios = [] to turn the scan off.",
            self._root,
            self.files_read,
        )

    def _note_unimportable_folder(self, directory: Path) -> None:
        """Log a folder skipped for its name when a file in it uses ``@scenario``.

        Folders the walk skips anyway (hidden, excluded by name, protected) are
        not looked into, and the files read count against the walk's limit.
        """
        resolved = directory.resolve()
        if skipped_directory_reason(directory=resolved, skipped_paths=self._skipped_paths):
            return
        decorated = self._decorated_file_within(
            directory=resolved, depth=_UNIMPORTABLE_FOLDER_LOOKAHEAD
        )
        if decorated is None:
            return
        logger.info(
            "Not scanning %s for scenarios: %r is not a Python identifier, so no file "
            "under it can be imported by module name, and %s uses @scenario. Rename "
            "the folder to load it.",
            resolved,
            resolved.name,
            decorated,
        )


def is_module_name_part(part: str) -> bool:
    """Return whether ``part`` can be one component of a dotted module name."""
    return part.isidentifier() and not keyword.iskeyword(part)


def _rename_advice(inside_project: bool, is_directory: bool) -> str:
    """Return what to do about a path that cannot be imported by module name."""
    if inside_project:
        return (
            "Inside the project every file is imported by its path from the project "
            "root, so rename the folder or file that is not one."
        )
    if is_directory:
        return "Rename it, or point the source at a directory closer to the file."
    return "Rename it."


def module_name_for(path: Path, import_root: Path, advice: str) -> str:
    """Return the dotted name ``path`` is imported as under ``import_root``.

    ``pkg/__init__.py`` is imported as ``pkg``. Raises
    :class:`ScenarioCatalogError`, ending with ``advice``, when the path is
    outside the root or a component cannot be part of a module name.
    """
    try:
        relative = path.relative_to(import_root)
    except ValueError as exc:
        logger.exception("%s is not under its import root %s", path, import_root)
        raise ScenarioCatalogError(f"{path} is not under {import_root}") from exc
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    if not parts or not all(is_module_name_part(part=part) for part in parts):
        raise ScenarioCatalogError(
            f"{path} cannot be imported by module name from {import_root}: every "
            f"directory and the file name must be a Python identifier. {advice}"
        )
    return ".".join(parts)


def import_file(
    path: Path, module_name: str, import_root: Path, source: FileSource | DirectorySource
) -> None:
    """Import ``path`` as ``module_name``, with ``import_root`` on ``sys.path``.

    The root goes on ``sys.path`` and stays there, so modules the file imports
    later resolve the same way. Raises :class:`ScenarioCatalogError` when the
    import fails, or when the name resolves to a different file, which happens
    when another module of the same top-level name is already importable.
    """
    problem = _import_problem(
        path=path, module_name=module_name, import_root=import_root, source=source
    )
    if problem is not None:
        raise ScenarioCatalogError(problem)


def _import_scanned_file(
    path: Path, import_root: Path, advice: str, source: DirectorySource
) -> str | None:
    """Import a file the project scan found and return its module name.

    Logs and returns None when the file has no module name under the root or
    fails to import.
    """
    try:
        module_name = module_name_for(path=path, import_root=import_root, advice=advice)
    except ScenarioCatalogError:
        logger.exception(
            "Skipping a file the scan of the project directory found: %s has no module "
            "name under %s. The scan carries on without it.",
            path,
            import_root,
        )
        return None
    problem = _import_problem(
        path=path, module_name=module_name, import_root=import_root, source=source
    )
    if problem is None:
        return module_name
    logger.warning(
        "Skipping a file the scan of the project directory found: %s The scan "
        "carries on without it. Name your scenario sources in [tool.glossogen] "
        "scenarios to have such a file stop the command instead.",
        problem,
    )
    return None


def _import_problem(
    path: Path, module_name: str, import_root: Path, source: FileSource | DirectorySource
) -> str | None:
    """Import ``path`` as ``module_name`` and return why that failed, or None.

    A failed import keeps no registration it made: a class registered by a file
    that then raised does not hold its name against a later file.
    """
    root_entry = str(import_root)
    if root_entry not in sys.path:
        sys.path.insert(0, root_entry)
    before = registrations_snapshot()
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        logger.exception("%s failed to import as %s", path, module_name)
        restore_registrations(snapshot=before)
        return (
            f"{path}, from scenario source {source.describe()}, failed to import as "
            f"{module_name}: {type(exc).__name__}: {exc}"
        )
    loaded_from = getattr(module, "__file__", None)
    if loaded_from is None or Path(loaded_from).resolve() != path.resolve():
        restore_registrations(snapshot=before)
        return (
            f"{path}, from scenario source {source.describe()}, is imported as "
            f"{module_name}, but that name resolves to {loaded_from}. Another module "
            f"named {module_name.split('.')[0]!r} is importable here; rename the folder."
        )
    return None
