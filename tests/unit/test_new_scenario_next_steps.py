"""The next steps `glossogen new-scenario` prints.

glossogen just ran, so telling the user to install it is wrong unless it ran from
outside the project or without its test extra. A uv project gets `uv add` and
`uv run` rather than pip.
"""

from pathlib import Path

from glossogen.cli.scenario_authoring_commands import is_uv_project, next_step_lines
from glossogen.scenario_contract.scenario_sources import ProjectLocation


def steps(
    project_root: Path, environment_prefix: Path, uses_uv: bool, has_pytest: bool
) -> list[str]:
    """Return the printed lines for a scenario `drill` in ``project_root``."""
    return next_step_lines(
        scenario_name="drill",
        scenario_folder="./drill",
        test_file="./drill/test_drill.py",
        working_dir=project_root,
        project=ProjectLocation(root=project_root, pyproject=project_root / "pyproject.toml"),
        uses_uv=uses_uv,
        environment_prefix=environment_prefix,
        has_pytest=has_pytest,
        glossogen_version="0.0.0",
    )


def test_no_install_step_when_glossogen_runs_from_the_project_environment(
    tmp_path: Path,
) -> None:
    """The project's own `.venv` ran glossogen and has pytest: nothing to install."""
    lines = steps(
        project_root=tmp_path,
        environment_prefix=tmp_path / ".venv",
        uses_uv=False,
        has_pytest=True,
    )

    assert not any("pip install" in line or "uv add" in line for line in lines)
    assert "  1. Put your provider key in" in lines[1]
    assert lines[-1] == "  4. pytest ./drill/test_drill.py"


def test_a_uv_project_gets_uv_run_commands(tmp_path: Path) -> None:
    """Each command runs in the project's environment through `uv run`."""
    lines = steps(
        project_root=tmp_path,
        environment_prefix=tmp_path / ".venv",
        uses_uv=True,
        has_pytest=True,
    )

    assert "  2. uv run glossogen validate ./drill" in lines
    assert lines[-1] == "  4. uv run pytest ./drill/test_drill.py"


def test_glossogen_from_outside_the_project_gets_the_install_step(tmp_path: Path) -> None:
    """A glossogen run from elsewhere (pipx, uvx, another venv) is not the project's."""
    project = tmp_path / "project"
    project.mkdir()

    pip_lines = steps(
        project_root=project,
        environment_prefix=tmp_path / "elsewhere",
        uses_uv=False,
        has_pytest=True,
    )
    uv_lines = steps(
        project_root=project,
        environment_prefix=tmp_path / "elsewhere",
        uses_uv=True,
        has_pytest=True,
    )

    assert any(line.strip().startswith('pip install "glossogen[testing]') for line in pip_lines)
    assert any(line.strip().startswith('uv add "glossogen[testing]') for line in uv_lines)


def test_a_missing_pytest_gets_the_test_extra(tmp_path: Path) -> None:
    """The project's environment has glossogen but not its `testing` extra."""
    lines = steps(
        project_root=tmp_path,
        environment_prefix=tmp_path / ".venv",
        uses_uv=False,
        has_pytest=False,
    )

    assert "  1. Add glossogen's test extra, which brings pytest:" in lines


def test_a_uv_project_is_recognised_by_its_lock_or_its_table(tmp_path: Path) -> None:
    """`uv.lock` beside the pyproject, or a `[tool.uv]` table in it."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "0"\n')
    project = ProjectLocation(root=tmp_path, pyproject=pyproject)
    assert not is_uv_project(project=project)

    pyproject.write_text('[project]\nname = "x"\nversion = "0"\n\n[tool.uv]\npackage = true\n')
    assert is_uv_project(project=project)

    pyproject.write_text('[project]\nname = "x"\nversion = "0"\n')
    (tmp_path / "uv.lock").write_text("")
    assert is_uv_project(project=project)
