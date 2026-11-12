"""Where a process's scenarios come from: the configured sources and the project scan.

Each test builds a project under ``tmp_path`` and loads a catalog from it. The
registry, the current catalog, ``sys.path`` and the modules a test imported are
restored afterwards, so module names can repeat across tests.
"""

import logging
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import glossogen
from glossogen.scenario_contract import scenario_source_kinds
from glossogen.scenario_contract.catalog import (
    ScenarioCatalog,
    ScenarioCatalogError,
    ScenarioNotLoaded,
    load_scenario_catalog,
)
from glossogen.scenario_contract.scenario_source_kinds import (
    DirectorySource,
    skipped_directory_reason,
)
from glossogen.scenario_contract.scenario_sources import (
    SCENARIOS_ENV_VAR,
    child_process_environment,
    resolve_scenario_sources,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def load(
    working_dir: Path,
    cli_sources: tuple[str, ...],
    environ: dict[str, str],
    runs_dirs: tuple[Path, ...],
) -> ScenarioCatalog:
    """Resolve the sources for ``working_dir`` and load them."""
    return load_scenario_catalog(
        sources=resolve_scenario_sources(
            cli_sources=cli_sources,
            environ=environ,
            working_dir=working_dir,
            runs_dirs=runs_dirs,
        )
    )


def loaded_from(loaded: ScenarioCatalog) -> list[str]:
    """Return the description of every source after the built-ins."""
    return [source.source.describe() for source in loaded.loaded_sources[1:]]


def test_with_nothing_configured_the_project_directory_is_scanned(tmp_path: Path) -> None:
    """A decorated file in a plain folder imports as ``folder.module``; helpers never run."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "[project]\nname = 'p'\n",
            "experiments/reactor.py": decorated_module(name="reactor"),
            "experiments/helper.py": (
                "# mentions glossogen.scenario_contract.registration\n"
                "raise RuntimeError('the scan ran a helper')\n"
            ),
            "experiments/sub/deeper.py": decorated_module(name="deeper"),
        },
    )

    loaded = load(working_dir=tmp_path / "experiments", cli_sources=(), environ={}, runs_dirs=())

    assert {"deeper", "reactor"} <= set(loaded.names())
    assert loaded.get(name="reactor").__module__ == "experiments.reactor"
    assert loaded.get(name="deeper").__module__ == "experiments.sub.deeper"
    assert loaded_from(loaded) == [
        f"{tmp_path.resolve()} (scan of the project directory; no sources configured)"
    ]


@pytest.mark.parametrize(
    "skipped",
    [
        "tests",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "site-packages",
        "_private",
        ".hidden",
        "build",
        "dist",
    ],
)
def test_the_scan_skips_directories_that_hold_no_scenarios(tmp_path: Path, skipped: str) -> None:
    """Environments, tests, build output, hidden and private folders are never read."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            f"{skipped}/scen.py": decorated_module(name="should_not_load"),
        },
    )

    loaded = load(working_dir=tmp_path, cli_sources=(), environ={}, runs_dirs=())

    assert loaded.find(name="should_not_load") is None


def test_a_scenario_file_inside_a_run_directory_is_never_imported(tmp_path: Path) -> None:
    """Bundle import extracts any file into a run directory, so the scan must not read one.

    The run directory sits in a folder no command names as its runs directory,
    and its name is a valid module name, so only its event log marks it as a run.
    """
    run_dir = tmp_path / "sweep_output" / "reactor" / "saved_run"
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "sweep_output/reactor/saved_run/reactor.jsonl": "",
            "sweep_output/reactor/saved_run/planted.py": decorated_module(name="planted"),
        },
    )

    loaded = load(working_dir=tmp_path, cli_sources=(), environ={}, runs_dirs=())

    assert loaded.find(name="planted") is None
    reason = skipped_directory_reason(directory=run_dir.resolve(), skipped_paths=frozenset())
    assert reason == "a run directory"


def test_the_same_directory_without_an_event_log_is_scanned(tmp_path: Path) -> None:
    """The control for the test above: the event log is what keeps the file out."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "sweep_output/reactor/saved_run/planted.py": decorated_module(name="planted"),
        },
    )

    loaded = load(working_dir=tmp_path, cli_sources=(), environ={}, runs_dirs=())

    assert loaded.find(name="planted") is not None


@pytest.mark.parametrize("configured_by", ["flag", "env", "default"])
def test_the_runs_directory_is_never_scanned(tmp_path: Path, configured_by: str) -> None:
    """``--runs-dir``, ``GLOSSOGEN_RUNS_DIR`` and the default ``./runs`` are all skipped."""
    runs_name = "runs"
    environ: dict[str, str] = {}
    runs_dirs: tuple[Path, ...] = ()
    if configured_by == "flag":
        runs_name = "my_runs"
        runs_dirs = (Path(runs_name),)
    if configured_by == "env":
        runs_name = "env_runs"
        environ = {"GLOSSOGEN_RUNS_DIR": runs_name}
    write(
        root=tmp_path,
        files={"pyproject.toml": "", f"{runs_name}/planted.py": decorated_module(name="planted")},
    )

    loaded = load(working_dir=tmp_path, cli_sources=(), environ=environ, runs_dirs=runs_dirs)

    assert loaded.find(name="planted") is None


def test_the_installed_glossogen_package_is_skipped_by_a_scan() -> None:
    """A scan of a glossogen checkout does not register the built-ins a second time."""
    sources = resolve_scenario_sources(
        cli_sources=(), environ={}, working_dir=REPO_ROOT, runs_dirs=()
    )

    scan = sources[-1]
    assert isinstance(scan, DirectorySource)
    assert Path(glossogen.__file__).parent.resolve() in scan.skipped_paths


def test_tool_glossogen_paths_are_relative_to_the_pyproject(tmp_path: Path) -> None:
    """Run from a subdirectory, the listed folder is still found beside pyproject.toml."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": '[tool.glossogen]\nscenarios = ["scenarios"]\n',
            "scenarios/listed.py": decorated_module(name="listed"),
            "elsewhere/unlisted.py": decorated_module(name="unlisted"),
            "notebooks/.keep": "",
        },
    )

    loaded = load(working_dir=tmp_path / "notebooks", cli_sources=(), environ={}, runs_dirs=())

    assert loaded.find(name="listed") is not None
    assert loaded.find(name="unlisted") is None
    assert loaded_from(loaded) == [
        f"scenarios ([tool.glossogen] in {tmp_path.resolve() / 'pyproject.toml'})"
    ]


@pytest.mark.parametrize("configured_by", ["pyproject", "env"])
def test_an_empty_list_turns_the_scan_off(tmp_path: Path, configured_by: str) -> None:
    """``scenarios = []`` and an empty ``GLOSSOGEN_SCENARIOS`` load the built-ins only."""
    pyproject = ""
    environ: dict[str, str] = {}
    if configured_by == "pyproject":
        pyproject = "[tool.glossogen]\nscenarios = []\n"
    else:
        environ = {SCENARIOS_ENV_VAR: ""}
    write(
        root=tmp_path,
        files={"pyproject.toml": pyproject, "scen.py": decorated_module(name="found")},
    )

    loaded = load(working_dir=tmp_path, cli_sources=(), environ=environ, runs_dirs=())

    assert loaded.find(name="found") is None
    assert loaded_from(loaded) == []


def test_the_flag_replaces_the_variable_which_replaces_the_pyproject(tmp_path: Path) -> None:
    """The first of flag, variable and pyproject decides; the others are not read."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": '[tool.glossogen]\nscenarios = ["from_pyproject"]\n',
            "from_pyproject/a.py": decorated_module(name="from_pyproject"),
            "from_env/b.py": decorated_module(name="from_env"),
            "from_flag/c.py": decorated_module(name="from_flag"),
        },
    )
    environ = {SCENARIOS_ENV_VAR: "from_env"}

    by_flag = load(working_dir=tmp_path, cli_sources=("from_flag",), environ=environ, runs_dirs=())
    assert {"from_flag"} == set(by_flag.names()) - set(by_flag.loaded_sources[0].scenario_names)
    assert loaded_from(by_flag) == ["from_flag (--scenarios)"]

    by_env = load(working_dir=tmp_path, cli_sources=(), environ=environ, runs_dirs=())
    assert loaded_from(by_env) == [f"from_env ({SCENARIOS_ENV_VAR})"]
    assert by_env.find(name="from_pyproject") is None


def test_a_module_name_source_scans_its_package() -> None:
    """Naming an installed package is enough: its scenario modules are found inside it."""
    loaded = load(
        working_dir=REPO_ROOT,
        cli_sources=("tests.fakes.external_scenario",),
        environ={},
        runs_dirs=(),
    )

    assert (
        loaded.get(name="external_scenario").__module__ == "tests.fakes.external_scenario.scenario"
    )
    assert loaded.loaded_sources[-1].child_entries == ("tests.fakes.external_scenario",)


def test_a_file_outside_the_project_imports_as_its_own_stem(tmp_path: Path) -> None:
    """With no project around it, the file's folder is its import root."""
    project = tmp_path / "project"
    write(root=project, files={"pyproject.toml": ""})
    write(root=tmp_path, files={"outside/lone_scenario.py": decorated_module(name="lone")})

    loaded = load(
        working_dir=project,
        cli_sources=(str(tmp_path / "outside" / "lone_scenario.py"),),
        environ={},
        runs_dirs=(),
    )

    assert loaded.get(name="lone").__module__ == "lone_scenario"


def test_a_child_gets_module_names_and_their_import_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The child imports the same modules under the same names, with no scan."""
    write(
        root=tmp_path,
        files={"pyproject.toml": "", "experiments/reactor.py": decorated_module(name="reactor")},
    )
    parent = load(working_dir=tmp_path, cli_sources=(), environ={}, runs_dirs=())
    monkeypatch.setenv(SCENARIOS_ENV_VAR, "ignored by the child")
    monkeypatch.setenv("PYTHONPATH", "/already/there")

    environment = child_process_environment()

    assert environment[SCENARIOS_ENV_VAR] == "experiments.reactor"
    assert environment["PYTHONPATH"] == os.pathsep.join([str(tmp_path.resolve()), "/already/there"])
    child = load(
        working_dir=tmp_path,
        cli_sources=(),
        environ={SCENARIOS_ENV_VAR: environment[SCENARIOS_ENV_VAR]},
        runs_dirs=(),
    )
    assert child.get(name="reactor") is parent.get(name="reactor")


def test_a_fresh_child_in_another_directory_keeps_the_package_context(tmp_path: Path) -> None:
    """A package outside the project, using a relative import, loads in a real child process.

    The child runs in a different working directory from the parent's project,
    as a server-launched run may.
    """
    write(root=tmp_path, files={"project/pyproject.toml": "", "elsewhere/.keep": ""})
    write(
        root=tmp_path / "outside",
        files={
            "pack/helper.py": "NAME = 'relative_child'\n",
            "pack/reactor.py": decorated_module(name="placeholder").replace(
                "@scenario(name='placeholder')",
                "from .helper import NAME\n\n\n@scenario(name=NAME)",
            ),
        },
    )
    load(
        working_dir=tmp_path / "project",
        cli_sources=(str(tmp_path / "outside" / "pack"),),
        environ={},
        runs_dirs=(),
    )
    environment = child_process_environment()

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from glossogen.scenario_contract.scenario_sources import "
            "load_configured_scenario_catalog\n"
            "loaded = load_configured_scenario_catalog(cli_sources=(), runs_dirs=())\n"
            "print(loaded.get(name='relative_child').__module__)\n",
        ],
        cwd=tmp_path / "elsewhere",
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == "pack.reactor"


def test_a_child_of_a_built_in_only_parent_scans_nothing(tmp_path: Path) -> None:
    """An empty variable is set, not unset, so the child does not fall back to a scan."""
    write(root=tmp_path, files={"pyproject.toml": "[tool.glossogen]\nscenarios = []\n"})
    load(working_dir=tmp_path, cli_sources=(), environ={}, runs_dirs=())

    assert child_process_environment()[SCENARIOS_ENV_VAR] == ""


def test_the_not_loaded_error_names_every_source_and_its_origin(tmp_path: Path) -> None:
    """The message says what was loaded, from where, and how to add the missing one."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": '[tool.glossogen]\nscenarios = ["scenarios"]\n',
            "scenarios/listed.py": decorated_module(name="listed"),
        },
    )
    loaded = load(working_dir=tmp_path, cli_sources=(), environ={}, runs_dirs=())

    with pytest.raises(ScenarioNotLoaded) as missing:
        loaded.get(name="reactor_purge")

    message = str(missing.value)
    assert "'reactor_purge' is not loaded" in message
    assert "glossogen.scenarios (built-in)" in message
    assert f"scenarios ([tool.glossogen] in {tmp_path.resolve() / 'pyproject.toml'})" in message
    assert "[tool.glossogen] scenarios" in message
    assert "--scenarios" in message


def test_a_source_that_is_neither_a_path_nor_a_module_is_refused(tmp_path: Path) -> None:
    """A typo in a path is reported, not silently treated as nothing to load."""
    with pytest.raises(ScenarioCatalogError, match="not a file or directory"):
        resolve_scenario_sources(
            cli_sources=("./no/such-dir",), environ={}, working_dir=tmp_path, runs_dirs=()
        )


def test_a_file_that_fails_to_import_is_named(tmp_path: Path) -> None:
    """The error says which file, from which source, and why."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "scen.py": decorated_module(name="broken") + "\nraise RuntimeError('boom')\n",
        },
    )

    with pytest.raises(ScenarioCatalogError) as refused:
        load(working_dir=tmp_path, cli_sources=(), environ={}, runs_dirs=())

    assert str(tmp_path.resolve() / "scen.py") in str(refused.value)
    assert "boom" in str(refused.value)


def test_two_files_registering_one_name_are_refused(tmp_path: Path) -> None:
    """A collision between configured sources is the user's mistake, and stops the load."""
    write(
        root=tmp_path,
        files={
            "pyproject.toml": "",
            "a/scen.py": decorated_module(name="twice"),
            "b/scen.py": decorated_module(name="twice"),
        },
    )

    with pytest.raises(ScenarioCatalogError, match="registered twice"):
        load(working_dir=tmp_path, cli_sources=(), environ={}, runs_dirs=())


def test_a_scan_reading_many_files_suggests_configuring_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Run from a home directory, the scan would walk everything; it says how to stop that."""
    monkeypatch.setattr(scenario_source_kinds, "LARGE_SCAN_FILE_COUNT", 2)
    write(
        root=tmp_path,
        files={"pyproject.toml": "", "a.py": "", "b.py": "", "c.py": ""},
    )

    with caplog.at_level(logging.WARNING):
        load(working_dir=tmp_path, cli_sources=(), environ={}, runs_dirs=())

    assert "read 3 .py files" in caplog.text
    assert "[tool.glossogen]" in caplog.text
