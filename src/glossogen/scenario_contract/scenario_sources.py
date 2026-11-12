"""Which scenario sources a process loads, resolved once at startup.

The built-in package always comes first. After it, the first of these that is
set decides the rest:

1. ``--scenarios <source>`` on the command line, repeatable;
2. ``GLOSSOGEN_SCENARIOS``, ``os.pathsep``-separated;
3. ``[tool.glossogen] scenarios = [...]`` in the nearest ``pyproject.toml`` at or
   above the working directory, with paths relative to that file.

When none is set, the project directory is scanned: the directory holding that
``pyproject.toml``, or the working directory when there is none. An empty list in
any of the three, ``scenarios = []`` and ``--scenarios ""`` included, means no
scan.

A source is a path when it names an existing file or directory, and a module
name otherwise. Nothing here reads a run's data: what a process imports comes
only from its own command line, environment and project file.

A child ``glossogen`` process gets ``GLOSSOGEN_SCENARIOS`` set to the modules its
parent loaded, and ``PYTHONPATH`` extended with the directories they import from
(:func:`child_process_environment`), so it imports the same modules under the
same names whatever its working directory, without scanning.
"""

import logging
import os
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NamedTuple, cast

import glossogen
from glossogen.scenario_contract.catalog import (
    SINGLE_MODULE_ENTRY_SUFFIX,
    ScenarioCatalog,
    ScenarioCatalogError,
    ScenarioSource,
    built_in_scenario_sources,
    current_scenario_catalog,
    is_scenario_catalog_loaded,
    load_scenario_catalog,
)
from glossogen.scenario_contract.scenario_source_kinds import (
    DirectorySource,
    FileSource,
    ModuleSource,
    SingleModuleSource,
    is_module_name_part,
)

logger = logging.getLogger(__name__)

SCENARIOS_ENV_VAR = "GLOSSOGEN_SCENARIOS"
PYTHON_PATH_ENV_VAR = "PYTHONPATH"
RUNS_DIR_ENV_VAR = "GLOSSOGEN_RUNS_DIR"
PYPROJECT_NAME = "pyproject.toml"

# The runs directory the CLI commands default to, relative to the working
# directory. Skipped by every scan whether or not the command names it, under the
# project root as well as under the working directory.
DEFAULT_RUNS_DIR_NAME = "runs"


class ProjectLocation(NamedTuple):
    """The project a process runs in.

    ``root`` is the directory holding the nearest ``pyproject.toml``, or the
    working directory when there is none, in which case ``pyproject`` is None.
    """

    root: Path
    pyproject: Path | None


def find_project(working_dir: Path) -> ProjectLocation:
    """Return the project ``working_dir`` belongs to, walking up to the nearest pyproject."""
    resolved = working_dir.resolve()
    for directory in (resolved, *resolved.parents):
        candidate = directory / PYPROJECT_NAME
        if candidate.is_file():
            return ProjectLocation(root=directory, pyproject=candidate)
    return ProjectLocation(root=resolved, pyproject=None)


def resolve_scenario_sources(
    cli_sources: Sequence[str],
    environ: Mapping[str, str],
    working_dir: Path,
    runs_dirs: Sequence[Path],
) -> tuple[ScenarioSource, ...]:
    """Return the sources this process loads: the built-ins, then the configured ones.

    ``runs_dirs`` are the runs directories the command reads or writes; every
    directory source skips them, read relative to the working directory and to
    the project root, as it does the installed glossogen package. Blank
    ``--scenarios`` values are ignored, so ``--scenarios ""`` loads the built-ins
    only.
    Raises :class:`ScenarioCatalogError` for a source that is neither an existing
    path nor a module name, or a ``[tool.glossogen]`` table that cannot be read.
    """
    project = find_project(working_dir=working_dir)
    skipped = _skipped_paths(
        working_dir=working_dir,
        project_root=project.root,
        environ=environ,
        runs_dirs=runs_dirs,
    )
    builder = _SourceBuilder(project_root=project.root, skipped_paths=skipped)
    if cli_sources:
        configured = [
            builder.source_for(spec=spec, base_dir=working_dir, origin="--scenarios")
            for spec in cli_sources
            if spec.strip()
        ]
    elif SCENARIOS_ENV_VAR in environ:
        configured = [
            builder.source_for(spec=spec, base_dir=working_dir, origin=SCENARIOS_ENV_VAR)
            for spec in environ[SCENARIOS_ENV_VAR].split(os.pathsep)
            if spec.strip()
        ]
    else:
        configured = _pyproject_sources(project=project, builder=builder)
    return (*built_in_scenario_sources(), *configured)


def path_source(path: Path, working_dir: Path, origin: str) -> ScenarioSource:
    """Return the file or directory source for ``path``, imported as a configured one is.

    Raises :class:`ScenarioCatalogError` when ``path`` is neither an existing
    ``.py`` file nor a directory.
    """
    project = find_project(working_dir=working_dir)
    builder = _SourceBuilder(
        project_root=project.root,
        skipped_paths=_skipped_paths(
            working_dir=working_dir,
            project_root=project.root,
            environ=os.environ,
            runs_dirs=(),
        ),
    )
    resolved = (working_dir / path).resolve()
    if not resolved.exists():
        raise ScenarioCatalogError(f"{path} does not exist.")
    return builder.source_for(spec=str(path), base_dir=working_dir, origin=origin)


def load_configured_scenario_catalog(
    cli_sources: Sequence[str], runs_dirs: Sequence[Path]
) -> ScenarioCatalog:
    """Resolve this process's sources from its environment and load the catalog."""
    return load_scenario_catalog(
        sources=resolve_scenario_sources(
            cli_sources=cli_sources,
            environ=os.environ,
            working_dir=Path.cwd(),
            runs_dirs=runs_dirs,
        )
    )


def load_configured_scenario_catalog_unless_loaded() -> None:
    """Load the configured catalog, unless this process already loaded one.

    For code that can run either under the CLI, which has loaded the catalog by
    then, or on its own: the server module uvicorn imports, and the testing
    helpers a scenario's own test suite calls. The runs directory skipped is the
    one ``GLOSSOGEN_RUNS_DIR`` names, besides the default.
    """
    if is_scenario_catalog_loaded():
        return
    load_configured_scenario_catalog(cli_sources=(), runs_dirs=())


def child_process_environment() -> dict[str, str]:
    """Return this process's environment, set up for a ``glossogen`` child.

    ``GLOSSOGEN_SCENARIOS`` lists the modules the current catalog loaded beyond
    the built-ins, by name, and ``PYTHONPATH`` starts with the directories the
    file and directory sources imported them from. The child imports the same
    modules under the same names, so a relative import inside a scenario package
    works there too, without resolving or scanning anything.
    """
    catalog = current_scenario_catalog()
    environment = dict(os.environ)
    environment[SCENARIOS_ENV_VAR] = catalog.child_scenario_sources()
    python_path = catalog.child_import_roots()
    existing = environment.get(PYTHON_PATH_ENV_VAR)
    if existing:
        python_path.append(existing)
    if python_path:
        environment[PYTHON_PATH_ENV_VAR] = os.pathsep.join(python_path)
    return environment


def _skipped_paths(
    working_dir: Path,
    project_root: Path,
    environ: Mapping[str, str],
    runs_dirs: Sequence[Path],
) -> frozenset[Path]:
    """Return the directories a directory source never descends into, resolved.

    Each runs directory is read relative to the working directory and to the
    project root, so the project's ``runs/`` is skipped from any subdirectory.
    An absolute one is the same path either way.
    """
    relative = [Path(DEFAULT_RUNS_DIR_NAME), *runs_dirs]
    configured_runs_dir = environ.get(RUNS_DIR_ENV_VAR)
    if configured_runs_dir:
        relative.append(Path(configured_runs_dir))
    candidates = [Path(glossogen.__file__).parent]
    for runs_dir in relative:
        candidates.extend((working_dir / runs_dir, project_root / runs_dir))
    return frozenset(candidate.resolve() for candidate in candidates)


class _SourceBuilder(NamedTuple):
    """Turns a source as written into a :class:`ScenarioSource`."""

    project_root: Path
    skipped_paths: frozenset[Path]

    def source_for(self, spec: str, base_dir: Path, origin: str) -> ScenarioSource:
        """Return the source ``spec`` names, reading a path relative to ``base_dir``."""
        stripped = spec.strip()
        path = (base_dir / stripped).resolve()
        if path.is_file():
            if path.suffix != ".py":
                raise ScenarioCatalogError(
                    f"Scenario source {stripped!r} ({origin}) is a file but not a .py file."
                )
            return FileSource(
                path=path,
                import_root=self._import_root(path=path),
                inside_project=self._inside_project(path=path),
                spec=stripped,
                origin=origin,
            )
        if path.is_dir():
            return DirectorySource(
                path=path,
                import_root=self._import_root(path=path),
                skipped_paths=self.skipped_paths,
                inside_project=self._inside_project(path=path),
                is_project_scan=False,
                spec=stripped,
                origin=origin,
            )
        if stripped and all(is_module_name_part(part=part) for part in stripped.split(".")):
            if stripped.endswith(SINGLE_MODULE_ENTRY_SUFFIX):
                return SingleModuleSource(
                    module=stripped.removesuffix(SINGLE_MODULE_ENTRY_SUFFIX), origin=origin
                )
            return ModuleSource(module=stripped, origin=origin)
        raise ScenarioCatalogError(
            f"Scenario source {stripped!r} ({origin}) is not a file or directory under "
            f"{base_dir}, and not a module name."
        )

    def directory_scan(self) -> ScenarioSource:
        """Return the scan of the project directory, used when nothing is configured."""
        return DirectorySource(
            path=self.project_root,
            import_root=self.project_root,
            skipped_paths=self.skipped_paths,
            inside_project=True,
            is_project_scan=True,
            spec=str(self.project_root),
            origin="scan of the project directory; no sources configured",
        )

    def _import_root(self, path: Path) -> Path:
        """Return the directory ``path`` is imported relative to.

        The project root when the path is inside it. Otherwise the path's parent,
        so a file outside the project imports as its own stem and a directory as
        its own name.
        """
        if self._inside_project(path=path):
            return self.project_root
        return path.parent

    def _inside_project(self, path: Path) -> bool:
        """Return whether ``path`` is the project root or under it."""
        return path == self.project_root or self.project_root in path.parents


def _pyproject_sources(project: ProjectLocation, builder: _SourceBuilder) -> list[ScenarioSource]:
    """Return the sources ``[tool.glossogen] scenarios`` lists, or the project scan.

    With no ``pyproject.toml`` the scan starts at the working directory, which
    may be far more than a project, so that is logged before the walk starts.
    """
    if project.pyproject is None:
        logger.warning(
            "No pyproject.toml at or above %s, so the scan for scenarios starts there "
            "and reads every .py file below it. Add a pyproject.toml with "
            "[tool.glossogen] scenarios naming where scenarios live (scenarios = [] "
            "for none), or set GLOSSOGEN_SCENARIOS.",
            project.root,
        )
        return [builder.directory_scan()]
    try:
        document = tomllib.loads(project.pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        logger.exception("Could not parse %s", project.pyproject)
        raise ScenarioCatalogError(
            f"{project.pyproject} is not valid TOML, so its [tool.glossogen] scenarios "
            f"cannot be read: {exc}"
        ) from exc
    tool = document.get("tool")
    table: object = None
    if isinstance(tool, dict):
        table = cast(dict[str, object], tool).get("glossogen")
    if not isinstance(table, dict) or "scenarios" not in table:
        return [builder.directory_scan()]
    listed = cast(dict[str, object], table)["scenarios"]
    if not isinstance(listed, list) or not all(
        isinstance(item, str) for item in cast(list[object], listed)
    ):
        raise ScenarioCatalogError(
            f"[tool.glossogen] scenarios in {project.pyproject} must be a list of strings."
        )
    origin = f"[tool.glossogen] in {project.pyproject}"
    return [
        builder.source_for(spec=spec, base_dir=project.root, origin=origin)
        for spec in cast(list[str], listed)
    ]
