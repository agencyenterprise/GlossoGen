"""Write a runnable scenario package, for someone starting from nothing.

A scenario is a package layout, an entry point, a knobs model, a preset, prompt
templates and a handful of methods that have to agree with each other. Reading
that out of a guide and typing it is where an author's first hour goes, and two
of the steps fail long after the mistake: `package-data` omitted installs a wheel
that renders no prompt, and an entry-point key that disagrees with `name()` puts
runs in a directory `evaluate` will not look in.

So the generated package is one that already works: `check-scenario` passes,
`pytest` passes, and `glossogen run` completes. Editing something and watching it
break is a faster way to learn a contract than assembling it from nothing.

Templates are rendered with `<<name>>` delimiters rather than Jinja's own, so the
prompt templates they emit keep their `{{ }}` for the platform to render later.
"""

import re
from importlib import metadata
from pathlib import Path
from typing import NamedTuple

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from glossogen.scenario_entry_points import SCENARIO_ENTRY_POINT_GROUP
from glossogen.scenario_loader import available_scenario_names

TEMPLATES_DIR = Path(__file__).parent / "scaffold_templates"

# The scenario name is a Python module name, an entry-point key and a directory,
# so it has to be a plain lowercase identifier.
_VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class ScaffoldedPackage(NamedTuple):
    """Where the package landed, and what was written into it."""

    package_dir: Path
    files: tuple[Path, ...]


class ScaffoldError(Exception):
    """Raised when the package cannot be written, with the reason for a user."""


def scenario_class_prefix(scenario_name: str) -> str:
    """Return the CamelCase stem the generated classes are named from."""
    return "".join(part.capitalize() for part in scenario_name.split("_"))


def distribution_name(scenario_name: str) -> str:
    """Return the distribution name, which spells underscores as hyphens."""
    return scenario_name.replace("_", "-")


def default_glossogen_ref() -> str:
    """Return the release tag matching the installed glossogen.

    The generated `pyproject.toml` pins this rather than a branch, because the
    scenario contract can change between releases and a plug-in should be
    validated against the platform it was written for.
    """
    return f"v{metadata.version('glossogen')}"


def check_scenario_name(scenario_name: str) -> None:
    """Raise ``ScaffoldError`` unless the name can be used everywhere it is used."""
    if not _VALID_NAME.match(scenario_name):
        raise ScaffoldError(
            f"{scenario_name!r} is not usable as a scenario name. It becomes a Python "
            "module, an entry-point key and a directory, so it has to start with a "
            "lowercase letter and hold only lowercase letters, digits and underscores."
        )
    if scenario_name in available_scenario_names():
        raise ScaffoldError(
            f"{scenario_name!r} is already a scenario in this environment. A name "
            "already taken stays with the scenario that holds it, so this package "
            "would install and never resolve. Pick another name."
        )


def write_scenario_package(
    scenario_name: str, target_dir: Path, glossogen_ref: str
) -> ScaffoldedPackage:
    """Write the package for ``scenario_name`` under ``target_dir``.

    Raises ``ScaffoldError`` when the name is unusable, when it is taken by an
    installed scenario, or when the destination already exists. Nothing is
    written until every check has passed, so a refusal leaves no partial package.
    """
    check_scenario_name(scenario_name)

    package_dir = target_dir / distribution_name(scenario_name)
    if package_dir.exists():
        raise ScaffoldError(f"{package_dir} already exists. Move it aside or pick another name.")

    variables = {
        "scenario_name": scenario_name,
        "class_prefix": scenario_class_prefix(scenario_name),
        "distribution_name": distribution_name(scenario_name),
        "glossogen_ref": glossogen_ref,
        "entry_point_group": SCENARIO_ENTRY_POINT_GROUP,
    }

    written: list[Path] = []
    for template_name, relative_path in _destinations(scenario_name=scenario_name).items():
        destination = package_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            _render(template_name=template_name, variables=variables), encoding="utf-8"
        )
        written.append(destination)

    # Empty, and it has to stay that way: discovery imports submodules of this
    # package while the event union is still being built.
    init = package_dir / scenario_name / "__init__.py"
    init.write_text("", encoding="utf-8")
    written.append(init)

    return ScaffoldedPackage(package_dir=package_dir, files=tuple(sorted(written)))


def _destinations(scenario_name: str) -> dict[str, Path]:
    """Map each template to where its output belongs in the new package."""
    module = Path(scenario_name)
    return {
        "pyproject.toml.jinja": Path("pyproject.toml"),
        "README.md.jinja": Path("README.md"),
        "env.example.jinja": Path(".env.example"),
        "gitignore.jinja": Path(".gitignore"),
        "ids.py.jinja": module / "ids.py",
        "knobs.py.jinja": module / "knobs.py",
        "events.py.jinja": module / "events.py",
        "team_declaration.py.jinja": module / "team_declaration.py",
        "world.py.jinja": module / "world.py",
        "scenario.py.jinja": module / "scenario.py",
        "knobs_default.json.jinja": module / "knobs_default.json",
        "prompts/briefer_system.jinja.jinja": module / "prompts" / "briefer_system.jinja",
        "prompts/relay_system.jinja.jinja": module / "prompts" / "relay_system.jinja",
        "test_scenario.py.jinja": Path("tests") / f"test_{scenario_name}.py",
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
