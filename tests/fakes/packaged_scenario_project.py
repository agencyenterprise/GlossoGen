"""A generated scenario folder inside a project that builds a wheel.

`new-scenario` writes only the scenario's folder. The checks `validate <path>`
runs on a packaged project need the project around it, so this writes one: a
`pyproject.toml` with a `[build-system]`, the `package-data` the scenario guide
recommends, and `[tool.glossogen] scenarios` naming the folder that holds the
scenario folders. Tests break one thing in it and check what is reported.
"""

from pathlib import Path

from glossogen.scenario_authoring.scenario_scaffold import write_scenario_folder

PACKAGED_PYPROJECT = """\
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "packaged-scenarios"
version = "0.1.0"

[tool.glossogen]
scenarios = ["scenarios"]

[tool.setuptools.packages.find]
where = ["."]
include = ["scenarios*"]

[tool.setuptools.package-data]
"*" = [
    "**/*.jinja",
    "**/*.json",
]

"""

SCENARIOS_FOLDER = "scenarios"


def write_packaged_project(target: Path, scenario_name: str) -> Path:
    """Write ``target/project`` with the scenario in ``scenarios/<name>/``, and return it."""
    project = target / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(PACKAGED_PYPROJECT, encoding="utf-8")
    write_scenario_folder(scenario_name=scenario_name, target_dir=project / SCENARIOS_FOLDER)
    return project
