"""Write a runnable scenario folder, for someone starting from nothing.

A scenario is a decorated class, a knobs model, a preset, prompt templates and a
handful of methods that have to agree with each other. Reading that out of a
guide and typing it is where an author's first hour goes.

So the generated folder is one that already works: `validate` passes, its test
passes, and `glossogen run` completes. Editing something and watching it break is
a faster way to learn a contract than assembling it from nothing.

Only the scenario's own folder is written. Where it sits in the author's project,
and how that project is configured, is theirs; the default scan of the project
directory finds the folder without configuration, and
:func:`sources_reach` says whether the sources of the directory the command
ran in import it.

Templates are rendered with `<<name>>` delimiters rather than Jinja's own, so the
prompt templates they emit keep their `{{ }}` for the platform to render later.
"""

import importlib.util
import logging
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import NamedTuple

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from glossogen.scenario_contract.catalog import (
    ScenarioCatalogError,
    ScenarioSource,
    built_in_scenario_sources,
)
from glossogen.scenario_contract.loader import available_scenario_names
from glossogen.scenario_contract.scenario_name import is_valid_scenario_name

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "scaffold_templates"


class ScaffoldedScenario(NamedTuple):
    """Where the scenario folder landed, and what was written into it."""

    scenario_dir: Path
    module_path: Path
    test_path: Path
    files: tuple[Path, ...]


class ScaffoldError(Exception):
    """Raised when the folder cannot be written, with the reason for a user."""


def scenario_class_prefix(scenario_name: str) -> str:
    """Return the CamelCase stem the generated classes are named from."""
    return "".join(part.capitalize() for part in scenario_name.split("_"))


def check_scenario_name(scenario_name: str) -> None:
    """Raise ``ScaffoldError`` unless the name can be used everywhere it is used.

    Besides its shape, the name must not be a loaded scenario's, nor a module
    this process can already import: the standard library, an installed
    package, or a folder on the import path.
    """
    if not is_valid_scenario_name(name=scenario_name):
        raise ScaffoldError(
            f"{scenario_name!r} is not usable as a scenario name. It becomes a Python "
            "module, a folder and a run directory, so it has to start with a "
            "lowercase letter and hold only lowercase letters, digits and underscores."
        )
    if scenario_name in available_scenario_names():
        raise ScaffoldError(
            f"{scenario_name!r} is already a scenario this process loads. Two classes "
            "registering one name stop every glossogen command that loads both. Pick "
            "another name."
        )
    shadowed = importlib.util.find_spec(scenario_name)
    if shadowed is not None:
        raise ScaffoldError(
            f"{scenario_name!r} is already an importable module here "
            f"({_spec_location(spec=shadowed)}). The scenario folder would be imported "
            f"under the same name, so it would hide that module, or that module would "
            "hide the folder, and glossogen commands, tests and libraries that import "
            f"{scenario_name!r} would break. Pick another name."
        )


def _spec_location(spec: ModuleSpec) -> str:
    """Return where a module spec points: its file, its folders, or how it is provided."""
    if spec.has_location and spec.origin is not None:
        return spec.origin
    if spec.submodule_search_locations:
        return ", ".join(str(location) for location in spec.submodule_search_locations)
    if spec.origin is not None:
        return spec.origin
    return "no file"


def write_scenario_folder(scenario_name: str, target_dir: Path) -> ScaffoldedScenario:
    """Write the folder for ``scenario_name`` as ``target_dir/<scenario_name>/``.

    Raises ``ScaffoldError`` when the destination already exists, when the name
    is unusable, when a loaded scenario holds it, or when it is already an
    importable module. Nothing is written until
    every check has passed, so a refusal leaves no partial folder.
    """
    scenario_dir = target_dir / scenario_name
    if scenario_dir.exists():
        raise ScaffoldError(f"{scenario_dir} already exists. Move it aside or pick another name.")
    check_scenario_name(scenario_name=scenario_name)

    variables = {
        "scenario_name": scenario_name,
        "class_prefix": scenario_class_prefix(scenario_name),
    }

    written: list[Path] = []
    for template_name, relative_path in _destinations(scenario_name=scenario_name).items():
        destination = scenario_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            _render(template_name=template_name, variables=variables), encoding="utf-8"
        )
        written.append(destination)

    return ScaffoldedScenario(
        scenario_dir=scenario_dir,
        module_path=scenario_dir / f"{scenario_name}.py",
        test_path=scenario_dir / f"test_{scenario_name}.py",
        files=tuple(sorted(written)),
    )


class SourceReach(NamedTuple):
    """Whether the configured sources import a module, and why not if a source failed.

    ``failure`` is the error of the first configured source that failed to
    import, or None when every source imported.
    """

    reached: bool
    failure: str | None


def sources_reach(module_path: Path, sources: tuple[ScenarioSource, ...]) -> SourceReach:
    """Import every configured source in ``sources`` and say whether one imports ``module_path``.

    Asks the loader rather than predicting it, so every source kind and every
    rule a walk or an import applies counts the same way it will for the next
    command. Importing a source again re-reads its directory, so a module written
    after the catalog loaded is found. The built-in sources are skipped.
    """
    resolved = module_path.resolve()
    for source in configured_sources(sources=sources):
        try:
            imported = source.import_scenario_modules()
        except ScenarioCatalogError as failure:
            logger.exception("Scenario source %s failed to import", source.describe())
            return SourceReach(reached=False, failure=str(failure))
        for module_name in imported.module_names:
            loaded_from = getattr(sys.modules.get(module_name), "__file__", None)
            if loaded_from is not None and Path(loaded_from).resolve() == resolved:
                return SourceReach(reached=True, failure=None)
    return SourceReach(reached=False, failure=None)


def configured_sources(sources: tuple[ScenarioSource, ...]) -> tuple[ScenarioSource, ...]:
    """Return ``sources`` without the built-in ones."""
    built_ins = built_in_scenario_sources()
    return tuple(source for source in sources if source not in built_ins)


def _destinations(scenario_name: str) -> dict[str, Path]:
    """Map each template to where its output belongs in the scenario folder."""
    return {
        "package_init.py.jinja": Path("__init__.py"),
        "scenario_module.py.jinja": Path(f"{scenario_name}.py"),
        "knobs_default.json.jinja": Path("knobs_default.json"),
        "prompts/briefer_system.jinja.jinja": Path("prompts") / "briefer_system.jinja",
        "prompts/relay_system.jinja.jinja": Path("prompts") / "relay_system.jinja",
        "test_scenario.py.jinja": Path(f"test_{scenario_name}.py"),
    }


def _render(template_name: str, variables: dict[str, str]) -> str:
    """Render one template.

    ``StrictUndefined`` so a template naming a variable nobody passes fails here
    rather than emitting a file with a hole in it.
    """
    environment = Environment(
        loader=FileSystemLoader(searchpath=TEMPLATES_DIR),
        variable_start_string="<<",
        variable_end_string=">>",
        block_start_string="<%",
        block_end_string="%>",
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    return environment.get_template(name=template_name).render(**variables)
