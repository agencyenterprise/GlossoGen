"""What `glossogen new-scenario` writes, and what it prints.

The generated folder is checked here for the things that fail late: that the
project scan reaches it without configuration, that the scan does not import its
test, and that the printed next steps say so when the configured sources would
not reach it. That the folder also *runs* is a separate test, in
tests/integration.
"""

from pathlib import Path

import pytest

from glossogen.cli.cli_entry import main
from glossogen.scenario_authoring.scenario_scaffold import (
    ScaffoldError,
    configured_sources,
    scenario_class_prefix,
    sources_reach,
    write_scenario_folder,
)
from glossogen.scenario_contract.catalog import ScenarioSource
from glossogen.scenario_contract.scenario_sources import resolve_scenario_sources

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
    folder = generate(tmp_path, SCENARIO)

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
    generate(tmp_path, SCENARIO)
    generate(tmp_path, "second_drill")

    assert sorted(path.name for path in tmp_path.iterdir()) == [SCENARIO, "second_drill"]


def test_the_module_registers_the_scenario_under_its_name(tmp_path: Path) -> None:
    """The decorator carries the name, which is also the event prefix."""
    module = (generate(tmp_path, SCENARIO) / f"{SCENARIO}.py").read_text()

    assert '@scenario(name="reactor_purge")' in module
    assert '"reactor_purge_round_opened"' in module
    assert "def event_types(cls)" in module


def test_the_generated_test_needs_no_pytest_configuration(tmp_path: Path) -> None:
    """A project without `asyncio_mode = "auto"` would error on an unmarked async test."""
    test_source = (generate(tmp_path, SCENARIO) / f"test_{SCENARIO}.py").read_text()

    assert test_source.count("async def test_") == test_source.count("@pytest.mark.asyncio")
    assert f"from {SCENARIO}" not in test_source, "the test looks the scenario up by name"


def test_the_prompt_templates_keep_their_own_placeholders(tmp_path: Path) -> None:
    """The scaffold renders with `<<>>`, so `{{ }}` survives into the output.

    A prompt whose placeholders were consumed at generation time renders a
    channel name of nothing, at the first turn of the first paid run.
    """
    folder = generate(tmp_path, SCENARIO)
    prompt = (folder / "prompts" / "briefer_system.jinja").read_text()

    assert "{{ channels[0].display_name }}" in prompt


@pytest.mark.parametrize("target", [".", "experiments"], ids=["at-root", "one-level-down"])
@pytest.mark.parametrize("with_pyproject", [False, True], ids=["no-pyproject", "pyproject"])
def test_the_project_scan_reaches_the_folder(
    tmp_path: Path, target: str, with_pyproject: bool
) -> None:
    """With no source configured, the scan of the project directory finds the module."""
    if with_pyproject:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0"\n')
    written = write_scenario_folder(scenario_name=SCENARIO, target_dir=tmp_path / target)

    assert sources_reach(
        module_path=written.module_path, sources=sources_from(working_dir=tmp_path)
    )


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_the_scan_imports_the_module_but_not_the_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The test file has no `@scenario`, so the scan's syntax-tree filter skips it."""
    generate(tmp_path, SCENARIO)
    monkeypatch.chdir(tmp_path)
    imported = [
        module
        for source in configured_sources(sources=sources_from(working_dir=tmp_path))
        for module in source.import_scenario_modules().module_names
    ]

    assert imported == [f"{SCENARIO}.{SCENARIO}"]


def test_sources_that_leave_the_folder_out_are_named(tmp_path: Path) -> None:
    """A `[tool.glossogen] scenarios` list turns the scan off, so a new folder needs adding."""
    (tmp_path / "pyproject.toml").write_text('[tool.glossogen]\nscenarios = ["elsewhere"]\n')
    (tmp_path / "elsewhere").mkdir()
    written = write_scenario_folder(scenario_name=SCENARIO, target_dir=tmp_path)

    sources = sources_from(working_dir=tmp_path)

    assert not sources_reach(module_path=written.module_path, sources=sources)
    assert [source.describe().split(" ")[0] for source in configured_sources(sources=sources)] == [
        "elsewhere"
    ]


def test_a_folder_the_scan_skips_is_reported(tmp_path: Path) -> None:
    """The scan never descends into `tests/`, so a scenario written there is not found."""
    written = write_scenario_folder(scenario_name=SCENARIO, target_dir=tmp_path / "tests")

    assert not sources_reach(
        module_path=written.module_path, sources=sources_from(working_dir=tmp_path)
    )


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_the_command_defaults_to_the_working_directory_and_prints_next_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Validate, run and pytest lines, with paths a user can paste from where they are."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GLOSSOGEN_SCENARIOS", raising=False)
    monkeypatch.setattr("sys.argv", ["glossogen", "new-scenario", SCENARIO])

    main()

    out = capsys.readouterr().out
    assert (tmp_path / SCENARIO / f"{SCENARIO}.py").is_file()
    assert "ANTHROPIC_API_KEY" in out
    assert f"glossogen validate ./{SCENARIO}\n" in out
    assert f"glossogen run {SCENARIO} --config knobs_default" in out
    assert f"pytest ./{SCENARIO}/test_{SCENARIO}.py" in out
    assert "do not reach" not in out


@pytest.mark.usefixtures("isolated_scenario_imports")
def test_the_command_says_when_the_sources_do_not_reach_the_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """It names the fix rather than writing the configuration itself."""
    (tmp_path / "pyproject.toml").write_text("[tool.glossogen]\nscenarios = []\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GLOSSOGEN_SCENARIOS", raising=False)
    monkeypatch.setattr("sys.argv", ["glossogen", "new-scenario", SCENARIO])

    main()

    out = capsys.readouterr().out
    assert f"do not reach ./{SCENARIO}" in out
    assert "none: only the built-in scenarios are loaded" in out
    assert "[tool.glossogen] scenarios" in out
    assert (tmp_path / "pyproject.toml").read_text() == "[tool.glossogen]\nscenarios = []\n"


def test_a_name_that_is_not_an_identifier_is_refused(tmp_path: Path) -> None:
    """It becomes a module, a folder and a run directory."""
    with pytest.raises(ScaffoldError) as refused:
        generate(tmp_path, "Reactor Purge")

    assert "lowercase" in str(refused.value)
    assert not list(tmp_path.iterdir()), "a refused name still wrote something"


def test_a_name_a_built_in_holds_is_refused(tmp_path: Path) -> None:
    """Two classes registering one name stop every command that loads both."""
    with pytest.raises(ScaffoldError) as refused:
        generate(tmp_path, "veyru")

    assert "already a scenario" in str(refused.value)


def test_an_existing_folder_is_not_written_over(tmp_path: Path) -> None:
    """Regenerating over a folder someone has edited would discard their work."""
    generate(tmp_path, SCENARIO)

    with pytest.raises(ScaffoldError) as refused:
        generate(tmp_path, SCENARIO)

    assert "already exists" in str(refused.value)


def test_the_class_prefix_derives_from_the_scenario_name() -> None:
    """One value spells the classes and the module."""
    assert scenario_class_prefix("reactor_purge") == "ReactorPurge"
