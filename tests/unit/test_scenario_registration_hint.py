"""The hint `assert_scenario_is_loaded` adds when pytest runs outside any project.

Run from inside a scenario's folder with no `pyproject.toml` above it, the scan of
the project directory is that folder, which does not load the scenario. The
failure then says where to run pytest from.
"""

from pathlib import Path

import pytest

from glossogen.testing.scenario_registration import (
    assert_scenario_is_loaded,
    working_directory_hint,
)


def test_no_pyproject_above_gives_the_hint(tmp_path: Path) -> None:
    """The scan covered the working directory alone, so the hint names the project root."""
    hint = working_directory_hint(working_dir=tmp_path, environ={})

    assert "Run pytest from the project root" in hint
    assert str(tmp_path) in hint


def test_a_pyproject_above_gives_no_hint(tmp_path: Path) -> None:
    """Inside a project the scan starts at its root wherever pytest runs."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n')
    scenario_folder = tmp_path / "reactor_purge"
    scenario_folder.mkdir()

    assert working_directory_hint(working_dir=scenario_folder, environ={}) == ""


def test_configured_sources_give_no_hint(tmp_path: Path) -> None:
    """With `GLOSSOGEN_SCENARIOS` set there is no scan to explain."""
    assert working_directory_hint(working_dir=tmp_path, environ={"GLOSSOGEN_SCENARIOS": ""}) == ""


def test_the_assertion_carries_the_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A scenario not loaded, from a directory with no project, fails with the hint."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GLOSSOGEN_SCENARIOS", raising=False)

    with pytest.raises(AssertionError, match="Run pytest from the project root"):
        assert_scenario_is_loaded(scenario_name="no_such_scenario")
