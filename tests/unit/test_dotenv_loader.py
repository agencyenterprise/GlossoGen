"""Tests for reading the `.env` beside the project a command was run from.

`python-dotenv`'s own default locates the file relative to the module that
called it. Installed as a dependency that is `site-packages`, so a project's
`.env` is never read and the failure is silent: the key is simply absent, and
the run fails later against the provider rather than here.
"""

import os
from pathlib import Path

import pytest

from glossogen.dotenv_loader import load_env_from_working_directory


def test_reads_the_env_file_in_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file next to the project, which is where someone puts it."""
    (tmp_path / ".env").write_text("GLOSSOGEN_TEST_KEY=from_project\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GLOSSOGEN_TEST_KEY", raising=False)

    loaded = load_env_from_working_directory()

    assert loaded == tmp_path / ".env"
    assert os.environ["GLOSSOGEN_TEST_KEY"] == "from_project"


def test_reads_it_from_a_subdirectory_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Commands get run from wherever the runs directory is convenient."""
    (tmp_path / ".env").write_text("GLOSSOGEN_TEST_KEY=from_project_root\n")
    nested = tmp_path / "experiments" / "sweep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    monkeypatch.delenv("GLOSSOGEN_TEST_KEY", raising=False)

    assert load_env_from_working_directory() == tmp_path / ".env"
    assert os.environ["GLOSSOGEN_TEST_KEY"] == "from_project_root"


def test_the_environment_wins_over_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A variable set for one command is not overwritten by the file."""
    (tmp_path / ".env").write_text("GLOSSOGEN_TEST_KEY=from_file\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GLOSSOGEN_TEST_KEY", "from_the_command")

    load_env_from_working_directory()

    assert os.environ["GLOSSOGEN_TEST_KEY"] == "from_the_command"


def test_no_env_file_is_not_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every variable can legitimately come from the environment instead."""
    monkeypatch.chdir(tmp_path)
    assert load_env_from_working_directory() is None
