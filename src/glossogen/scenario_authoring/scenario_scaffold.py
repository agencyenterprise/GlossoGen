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
ran in would not.

Templates are rendered with `<<name>>` delimiters rather than Jinja's own, so the
prompt templates they emit keep their `{{ }}` for the platform to render later.
"""

from pathlib import Path
from typing import NamedTuple

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from glossogen.scenario_contract.catalog import ScenarioSource, built_in_scenario_sources
from glossogen.scenario_contract.loader import available_scenario_names
from glossogen.scenario_contract.scenario_name import is_valid_scenario_name
from glossogen.scenario_contract.scenario_source_kinds import (
    DirectorySource,
    FileSource,
    is_module_name_part,
    skipped_directory_reason,
)

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
    """Raise ``ScaffoldError`` unless the name can be used everywhere it is used."""
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


def write_scenario_folder(scenario_name: str, target_dir: Path) -> ScaffoldedScenario:
    """Write the folder for ``scenario_name`` as ``target_dir/<scenario_name>/``.

    Raises ``ScaffoldError`` when the name is unusable, when a loaded scenario
    holds it, or when the destination already exists. Nothing is written until
    every check has passed, so a refusal leaves no partial folder.
    """
    check_scenario_name(scenario_name)

    scenario_dir = target_dir / scenario_name
    if scenario_dir.exists():
        raise ScaffoldError(f"{scenario_dir} already exists. Move it aside or pick another name.")

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


def sources_reach(module_path: Path, sources: tuple[ScenarioSource, ...]) -> bool:
    """Return whether one of ``sources`` would import ``module_path``.

    True when a file source names the module, or a directory source's walk
    reaches it: the module is under the directory, every folder on the way is
    one a walk descends into, and each is a module name part. Module and package
    sources are not followed, so a module only they would reach counts as
    unreached.
    """
    resolved = module_path.resolve()
    for source in sources:
        if isinstance(source, FileSource) and source.path.resolve() == resolved:
            return True
        if isinstance(source, DirectorySource) and _walk_reaches(
            source=source, module_path=resolved
        ):
            return True
    return False


def configured_sources(sources: tuple[ScenarioSource, ...]) -> tuple[ScenarioSource, ...]:
    """Return ``sources`` without the built-in ones."""
    built_ins = built_in_scenario_sources()
    return tuple(source for source in sources if source not in built_ins)


def _walk_reaches(source: DirectorySource, module_path: Path) -> bool:
    """Return whether walking ``source`` descends to the folder holding ``module_path``."""
    root = source.path.resolve()
    if root not in module_path.parents:
        return False
    folder = module_path.parent
    while True:
        if skipped_directory_reason(directory=folder, skipped_paths=source.skipped_paths):
            return False
        if folder == root:
            return True
        if not is_module_name_part(part=folder.name):
            return False
        folder = folder.parent


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
