"""One scenario file imported under two module names registers one scenario.

The project scan names a file by its path from the project root, so anything that
imports the same file by a shorter name defines the class a second time. That is
one definition, not two scenarios claiming one name.

The source folder is called ``pysrc`` rather than ``src`` because this
repository's own ``src`` is an importable package in the test process.
"""

import importlib
import sys
import textwrap
from pathlib import Path

import pytest

from glossogen.scenario_contract.catalog import (
    built_in_scenario_sources,
    load_scenario_catalog,
)
from glossogen.scenario_contract.path_loader import load_scenarios_from_path
from glossogen.scenario_contract.scenario_source_kinds import ModuleSource
from glossogen.scenario_contract.scenario_sources import resolve_scenario_sources
from glossogen.testing import assert_scenario_is_registered


@pytest.fixture(autouse=True)
def isolated(isolated_scenario_imports: None) -> None:
    """Every test here imports modules from ``tmp_path``."""
    _ = isolated_scenario_imports


def decorated_module(name: str) -> str:
    """Return a module registering a scenario called ``name``."""
    return textwrap.dedent(f"""
        from glossogen.scenario_contract.registration import scenario
        from glossogen.scenarios.veyru.scenario import VeyruScenario


        @scenario(name={name!r})
        class Scenario(VeyruScenario):
            pass
        """)


def write(root: Path, files: dict[str, str]) -> None:
    """Write ``files``, keyed by path relative to ``root``."""
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def src_layout_project(root: Path) -> None:
    """Write a project with ``pysrc/mypack/reactor_s/reactor_s.py`` registering ``reactor_s``."""
    write(
        root=root,
        files={
            "pyproject.toml": "[project]\nname = 'mypack'\n",
            "pysrc/mypack/__init__.py": "",
            "pysrc/mypack/reactor_s/__init__.py": "",
            "pysrc/mypack/reactor_s/reactor_s.py": decorated_module(name="reactor_s"),
        },
    )


def scan(working_dir: Path) -> None:
    """Load the catalog the project around ``working_dir`` configures."""
    load_scenario_catalog(
        sources=resolve_scenario_sources(
            cli_sources=(), environ={}, working_dir=working_dir, runs_dirs=()
        )
    )


def test_a_src_layout_pack_imported_by_its_own_tests_after_the_scan(tmp_path: Path) -> None:
    """The scan imports ``pysrc.mypack...``; the pack's tests import ``mypack...``."""
    src_layout_project(root=tmp_path)
    scan(working_dir=tmp_path)
    sys.path.insert(0, str(tmp_path / "pysrc"))

    module = importlib.import_module("mypack.reactor_s.reactor_s")

    assert_scenario_is_registered(scenario_cls=module.Scenario)


def test_validating_a_path_already_loaded_as_a_module_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``scenarios = ["mypack"]`` loaded it; ``validate pysrc/mypack/reactor_s`` loads it again."""
    src_layout_project(root=tmp_path)
    sys.path.insert(0, str(tmp_path / "pysrc"))
    monkeypatch.chdir(tmp_path)
    load_scenario_catalog(
        sources=(*built_in_scenario_sources(), ModuleSource(module="mypack", origin="test"))
    )

    loaded = load_scenarios_from_path(path=Path("pysrc") / "mypack" / "reactor_s")

    assert [scenario.name for scenario in loaded] == ["reactor_s"]


def test_a_test_importing_its_class_one_folder_down(tmp_path: Path) -> None:
    """A test beside the scenario imports ``deep_one.deep_one``; the scan imports it longer."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "[project]\nname = 'p'\n",
            "experiments/deep_one/__init__.py": "",
            "experiments/deep_one/deep_one.py": decorated_module(name="deep_one"),
        },
    )
    sys.path.insert(0, str(tmp_path / "experiments"))
    module = importlib.import_module("deep_one.deep_one")

    scan(working_dir=tmp_path)

    assert_scenario_is_registered(scenario_cls=module.Scenario)
