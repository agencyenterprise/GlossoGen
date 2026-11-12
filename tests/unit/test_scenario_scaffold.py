"""What `glossogen new-scenario` writes, and what it prints.

The generated folder is checked here for the things that fail late: that the
project scan reaches it without configuration, that the scan does not import its
test, and that the printed next steps say so when the configured sources would
not reach it. That the folder also *runs* is a separate test, in
tests/integration.
"""

import logging
import os
import shlex
import sys
from pathlib import Path

import pytest

from glossogen.cli.cli_entry import main
from glossogen.scenario_authoring import scenario_scaffold
from glossogen.scenario_authoring.scenario_scaffold import (
    ScaffoldError,
    SourceReach,
    configured_sources,
    scenario_class_prefix,
    sources_reach,
    write_scenario_folder,
)
from glossogen.scenario_contract import catalog
from glossogen.scenario_contract.catalog import (
    PackageScanSource,
    ScenarioSource,
    current_scenario_catalog,
)
from glossogen.scenario_contract.scenario_sources import resolve_scenario_sources
from glossogen.testing import assert_scenario_is_loaded
from tests.fakes.catalog_installation import scenario_catalog_installed

SCENARIO = "reactor_purge"


def generate(target: Path, scenario_name: str) -> Path:
    """Write a scenario folder and return it."""
    return write_scenario_folder(scenario_name=scenario_name, target_dir=target).scenario_dir


def sources_from(working_dir: Path) -> tuple[ScenarioSource, ...]:
    """Return the sources a process started in ``working_dir`` would load."""
    return resolve_scenario_sources(
        cli_sources=(), environ={}, working_dir=working_dir, runs_dirs=()
    )


def test_only_the_scenario_folder_is_written(tmp_path: Path) -> None:
    """Nothing outside `<target>/<name>/`: the project around it is the author's."""
    folder = generate(target=tmp_path, scenario_name=SCENARIO)

    assert folder == tmp_path / SCENARIO
    assert [path.name for path in tmp_path.iterdir()] == [SCENARIO]
    written = {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()}
    assert written == {
        "__init__.py",
        "knobs_default.json",
        "prompts/briefer_system.jinja",
        "prompts/relay_system.jinja",
        "reactor_purge.py",
        "test_reactor_purge.py",
    }


def test_a_second_scenario_goes_in_a_folder_beside_the_first(tmp_path: Path) -> None:
    """Each scenario reads its prompts and presets from its own folder."""
    generate(target=tmp_path, scenario_name=SCENARIO)
    generate(target=tmp_path, scenario_name="second_drill")

    assert sorted(path.name for path in tmp_path.iterdir()) == [SCENARIO, "second_drill"]


def test_the_module_registers_the_scenario_under_its_name(tmp_path: Path) -> None:
    """The decorator carries the name, which is also the event prefix."""
    module = (generate(target=tmp_path, scenario_name=SCENARIO) / f"{SCENARIO}.py").read_text()

    assert '@scenario(name="reactor_purge")' in module
    assert '"reactor_purge_round_opened"' in module
    assert "def event_types(cls)" in module


def test_the_generated_test_needs_no_pytest_plugin(tmp_path: Path) -> None:
    """The tests are sync and drive the harness with `asyncio.run`.

    An async test needs pytest-asyncio and, unmarked, `asyncio_mode = "auto"`;
    a sync one runs under plain pytest in a project with no pytest configuration.
    """
    test_source = (
        generate(target=tmp_path, scenario_name=SCENARIO) / f"test_{SCENARIO}.py"
    ).read_text()

    assert "async def test_" not in test_source
    assert "pytest.mark.asyncio" not in test_source
    assert "asyncio.run(" in test_source
    assert f"from {SCENARIO}" not in test_source, "the test looks the scenario up by name"


def test_the_prompt_templates_keep_their_own_placeholders(tmp_path: Path) -> None:
    """The scaffold renders with `<<>>`, so `{{ }}` survives into the output.

    A prompt whose placeholders were consumed at generation time renders a
    channel name of nothing, at the first turn of the first paid run.
    """
    folder = generate(target=tmp_path, scenario_name=SCENARIO)
    prompt = (folder / "prompts" / "briefer_system.jinja").read_text()

    assert "{{ channels[0].display_name }}" in prompt


@pytest.mark.parametrize("target", [".", "experiments"], ids=["at-root", "one-level-down"])
@pytest.mark.parametrize("with_pyproject", [False, True], ids=["no-pyproject", "pyproject"])
@pytest.mark.usefixtures("isolated_scenario_imports")
def test_the_project_scan_reaches_the_folder(
    tmp_path: Path, target: str, with_pyproject: bool
) -> None:
    """With no source configured, the scan of the project directory imports the module."""
    if with_pyproject:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n')
    written = write_scenario_folder(scenario_name=SCENARIO, target_dir=tmp_path / target)

    reach = sources_reach(
        module_path=written.module_path, sources=sources_from(working_dir=tmp_path)
    )

    assert reach == SourceReach(reached=True, failure=None)


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_the_scan_imports_the_module_but_not_the_test(tmp_path: Path) -> None:
    """The test file has no `@scenario`, so the scan's syntax-tree filter skips it."""
    generate(target=tmp_path, scenario_name=SCENARIO)

    imported = [
        module
        for source in configured_sources(sources=sources_from(working_dir=tmp_path))
        for module in source.import_scenario_modules().module_names
    ]

    assert imported == [f"{SCENARIO}.{SCENARIO}"]


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_sources_that_leave_the_folder_out_do_not_reach_it(tmp_path: Path) -> None:
    """A `[tool.glossogen] scenarios` list turns the scan off, so a new folder needs adding."""
    (tmp_path / "pyproject.toml").write_text('[tool.glossogen]\nscenarios = ["elsewhere"]\n')
    (tmp_path / "elsewhere").mkdir()
    written = write_scenario_folder(scenario_name=SCENARIO, target_dir=tmp_path)

    reach = sources_reach(
        module_path=written.module_path, sources=sources_from(working_dir=tmp_path)
    )

    assert reach == SourceReach(reached=False, failure=None)


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_a_folder_the_scan_skips_is_not_reached(tmp_path: Path) -> None:
    """The scan never descends into `tests/`, so a scenario written there is not found.

    Every source imports cleanly: a `failure` would also leave the scenario unreached,
    without the skip rule having been what kept the scan out.
    """
    written = write_scenario_folder(scenario_name=SCENARIO, target_dir=tmp_path / "tests")

    reach = sources_reach(
        module_path=written.module_path, sources=sources_from(working_dir=tmp_path)
    )

    assert reach == SourceReach(reached=False, failure=None)


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_a_source_whose_import_path_is_not_a_module_name_reports_the_loader_error(
    tmp_path: Path,
) -> None:
    """The walk reaches the folder, but `a-b` cannot be part of its module name.

    The source is a directory below the project root, which stays the import root,
    so the name is `a-b.experiments.<name>.<name>`. The check asks the loader, so
    it fails here as the next command would.
    """
    (tmp_path / "pyproject.toml").write_text('[tool.glossogen]\nscenarios = ["a-b/experiments"]\n')
    (tmp_path / "a-b" / "experiments").mkdir(parents=True)
    sources = sources_from(working_dir=tmp_path)
    written = write_scenario_folder(
        scenario_name=SCENARIO, target_dir=tmp_path / "a-b" / "experiments"
    )

    reach = sources_reach(module_path=written.module_path, sources=sources)

    assert not reach.reached
    assert reach.failure is not None
    assert "Python identifier" in reach.failure


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_a_package_named_as_a_module_source_reaches_a_folder_inside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A package source scans its subpackages, and the generated folder is one."""
    package = tmp_path / "src" / "review_pack"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    monkeypatch.setattr(sys, "path", [str(tmp_path / "src"), *sys.path])
    written = write_scenario_folder(scenario_name=SCENARIO, target_dir=package)

    reach = sources_reach(
        module_path=written.module_path,
        sources=resolve_scenario_sources(
            cli_sources=("review_pack",), environ={}, working_dir=tmp_path, runs_dirs=()
        ),
    )

    assert reach == SourceReach(reached=True, failure=None)


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_the_built_in_source_reaches_a_folder_written_into_its_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A folder written into the built-in package is loaded with nothing configured.

    That is `--target-dir src/glossogen/scenarios` in a glossogen checkout.

    A package on a temporary path stands in for the built-in one, since no test
    writes into the package the repo ships. The check once skipped the built-in
    sources and told the user to configure a folder that was already loaded.
    """
    package = tmp_path / "built_in_stand_in"
    package.mkdir()
    (package / "__init__.py").write_text("")
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    built_in = PackageScanSource(package="built_in_stand_in", origin="built-in")
    monkeypatch.setattr(scenario_scaffold, "built_in_scenario_sources", lambda: (built_in,))
    written = write_scenario_folder(scenario_name=SCENARIO, target_dir=package)

    reach = sources_reach(module_path=written.module_path, sources=(built_in,))

    assert reach == SourceReach(reached=True, failure=None)


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_importing_a_source_again_logs_its_registrations_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`validate <path>` loads the catalog a second time; the scan's line is not repeated."""
    generate(target=tmp_path, scenario_name=SCENARIO)
    [scan] = configured_sources(sources=sources_from(working_dir=tmp_path))

    with caplog.at_level(logging.INFO):
        scan.import_scenario_modules()
        scan.import_scenario_modules()

    registered = [r for r in caplog.records if r.getMessage().startswith("Registered scenarios")]
    assert len(registered) == 1


def assert_loaded_by_a_fresh_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Load the catalog the environment now configures, as a new test process would.

    Restores the current catalog and the run readers' event-type lookup afterwards.
    """
    with scenario_catalog_installed(catalog=current_scenario_catalog()):
        monkeypatch.setattr(catalog, "_current", None)
        assert_scenario_is_loaded(scenario_name=SCENARIO)


def run_new_scenario(
    working_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> str:
    """Run `glossogen new-scenario` in ``working_dir`` and return what it printed."""
    monkeypatch.chdir(working_dir)
    monkeypatch.setattr("sys.argv", ["glossogen", "new-scenario", SCENARIO])
    main()
    return capsys.readouterr().out


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_the_command_defaults_to_the_working_directory_and_prints_next_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Validate, run and pytest lines, with paths a user can paste from where they are."""
    monkeypatch.delenv("GLOSSOGEN_SCENARIOS", raising=False)

    out = run_new_scenario(working_dir=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert (tmp_path / SCENARIO / f"{SCENARIO}.py").is_file()
    assert "ANTHROPIC_API_KEY" in out
    assert f"glossogen validate ./{SCENARIO}\n" in out
    assert f"glossogen run {SCENARIO} --config knobs_default" in out
    assert f"pytest ./{SCENARIO}/test_{SCENARIO}.py" in out
    assert "do not load" not in out


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_the_pyproject_fix_is_relative_to_the_pyproject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Run from below the pyproject, the entry it names is the path from that file.

    Following the advice makes the configured sources load the scenario, which is
    what the generated test checks. The command itself writes no configuration.
    """
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.glossogen]\nscenarios = []\n")
    (tmp_path / "experiments").mkdir()
    monkeypatch.delenv("GLOSSOGEN_SCENARIOS", raising=False)

    out = run_new_scenario(
        working_dir=tmp_path / "experiments", monkeypatch=monkeypatch, capsys=capsys
    )

    assert f"do not load ./{SCENARIO}" in out
    assert (
        f'Add "experiments/{SCENARIO}" to [tool.glossogen] scenarios in {pyproject.resolve()}'
        in out
    )
    assert pyproject.read_text() == "[tool.glossogen]\nscenarios = []\n"
    pyproject.write_text(f'[tool.glossogen]\nscenarios = ["experiments/{SCENARIO}"]\n')
    assert_loaded_by_a_fresh_catalog(monkeypatch=monkeypatch)


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_an_environment_source_is_extended_for_every_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`GLOSSOGEN_SCENARIOS` outranks the pyproject, so the fix goes in it, for pytest too."""
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.setenv("GLOSSOGEN_SCENARIOS", str(tmp_path / "elsewhere"))

    out = run_new_scenario(working_dir=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    exported = [line.strip() for line in out.splitlines() if "export GLOSSOGEN_SCENARIOS=" in line]
    assert len(exported) == 1
    value = shlex.split(exported[0].removeprefix("export GLOSSOGEN_SCENARIOS="))[0]
    assert value.split(os.pathsep) == [
        str(tmp_path / "elsewhere"),
        str((tmp_path / SCENARIO).resolve()),
    ]
    monkeypatch.setenv("GLOSSOGEN_SCENARIOS", value)
    assert_loaded_by_a_fresh_catalog(monkeypatch=monkeypatch)


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_a_command_line_source_gives_pytest_the_folder_through_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """pytest takes no `--scenarios`, so its line sets `GLOSSOGEN_SCENARIOS` instead."""
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.delenv("GLOSSOGEN_SCENARIOS", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["glossogen", "--scenarios", "elsewhere", "new-scenario", SCENARIO]
    )

    main()

    out = capsys.readouterr().out
    assert f"Pass --scenarios ./{SCENARIO}" in out
    pytest_line = next(line.strip() for line in out.splitlines() if " pytest ./" in line)
    assignment, _, command = pytest_line.partition(" pytest ")
    assert command == f"./{SCENARIO}/test_{SCENARIO}.py"
    value = shlex.split(assignment.removeprefix("GLOSSOGEN_SCENARIOS="))[0]
    monkeypatch.setenv("GLOSSOGEN_SCENARIOS", value)
    assert_loaded_by_a_fresh_catalog(monkeypatch=monkeypatch)


def test_a_name_that_is_not_an_identifier_is_refused(tmp_path: Path) -> None:
    """It becomes a module, a folder and a run directory."""
    with pytest.raises(ScaffoldError) as refused:
        generate(target=tmp_path, scenario_name="Reactor Purge")

    assert "lowercase" in str(refused.value)
    assert not list(tmp_path.iterdir()), "a refused name still wrote something"


def test_a_name_a_built_in_holds_is_refused(tmp_path: Path) -> None:
    """Two classes registering one name stop every command that loads both."""
    with pytest.raises(ScaffoldError) as refused:
        generate(target=tmp_path, scenario_name="veyru")

    assert "already a scenario" in str(refused.value)


def test_an_existing_folder_is_not_written_over(tmp_path: Path) -> None:
    """Regenerating over a folder someone has edited would discard their work."""
    generate(target=tmp_path, scenario_name=SCENARIO)

    with pytest.raises(ScaffoldError) as refused:
        generate(target=tmp_path, scenario_name=SCENARIO)

    assert "already exists" in str(refused.value)


def test_the_class_prefix_derives_from_the_scenario_name() -> None:
    """One value spells the classes and the module."""
    assert scenario_class_prefix(scenario_name="reactor_purge") == "ReactorPurge"
