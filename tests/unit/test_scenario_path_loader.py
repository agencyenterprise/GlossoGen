"""Loading and checking the scenarios a file or directory registers, for `validate <path>`.

The scaffold is the fixture throughout. It writes a project that passes, so each
test breaks one thing in a copy of it and states what should be reported. That
keeps the tests about the checks rather than about a hand-built tree that may not
resemble what an author actually has.
"""

import re
from pathlib import Path

import pytest

from glossogen.scenario_authoring.scenario_conformance import CheckOutcome, check_scenario, failures
from glossogen.scenario_authoring.scenario_package_checks import check_scenario_package
from glossogen.scenario_authoring.scenario_scaffold import write_scenario_package
from glossogen.scenario_contract.loader import find_scenario_class
from glossogen.scenario_contract.path_loader import (
    PathLoadedScenario,
    ScenarioPathError,
    load_scenarios_from_path,
)

REF = "v9.9.9"
SCENARIO = "reactor_purge"


@pytest.fixture(autouse=True)
def isolated(isolated_scenario_imports: None) -> None:
    """Every test here imports a scaffolded project's modules."""
    _ = isolated_scenario_imports


def scaffold(target: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write the project every test starts from, enter it, and return its directory."""
    project = write_scenario_package(
        scenario_name=SCENARIO, target_dir=target, glossogen_ref=REF
    ).package_dir
    monkeypatch.chdir(project)
    return project


def edit_pyproject(project: Path, pattern: str, replacement: str) -> None:
    """Rewrite one thing in the generated pyproject."""
    path = project / "pyproject.toml"
    path.write_text(re.sub(pattern, replacement, path.read_text(), flags=re.S), encoding="utf-8")


def load_one(path: Path) -> PathLoadedScenario:
    """Load ``path`` and return the one scenario it registers."""
    loaded = load_scenarios_from_path(path=path)
    assert len(loaded) == 1
    return loaded[0]


def package_check(path: Path, name: str) -> CheckOutcome:
    """Return the named package check's outcome for the scenario ``path`` registers."""
    report = check_scenario_package(loaded=load_one(path=path))
    matching = [outcome for outcome in report.outcomes if outcome.check == name]
    assert matching, f"no check named {name!r} ran; got {[o.check for o in report.outcomes]}"
    return matching[0]


def test_a_scenario_file_loads_by_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No install and no configuration: the path is the source."""
    project = scaffold(target=tmp_path, monkeypatch=monkeypatch)

    loaded = load_one(path=Path("scenarios") / f"{SCENARIO}.py")

    assert loaded.name == SCENARIO
    assert loaded.scenario_cls.__module__ == f"scenarios.{SCENARIO}"
    assert loaded.module_dir == (project / "scenarios").resolve()
    assert loaded.package_name == "scenarios"
    assert loaded.project_dir == project.resolve()


def test_a_directory_loads_every_scenario_it_registers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A folder is scanned the way a configured directory source is."""
    scaffold(target=tmp_path, monkeypatch=monkeypatch)

    assert [one.name for one in load_scenarios_from_path(path=Path("."))] == [SCENARIO]


def test_the_loaded_scenario_resolves_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The checks that look a scenario up by name find the one the path registered."""
    scaffold(target=tmp_path, monkeypatch=monkeypatch)

    loaded = load_one(path=Path("scenarios") / f"{SCENARIO}.py")

    assert find_scenario_class(name=SCENARIO) is loaded.scenario_cls


def test_the_contract_checks_pass_on_a_scaffolded_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path-loaded class goes through the same checks as a configured one."""
    scaffold(target=tmp_path, monkeypatch=monkeypatch)
    loaded = load_one(path=Path("scenarios") / f"{SCENARIO}.py")

    broken = failures(check_scenario(scenario_cls=loaded.scenario_cls))

    assert not broken, [f"{one.check} — {one.detail}" for one in broken]


def test_package_data_passes_on_a_scaffolded_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The scaffold's package-data covers its prompts and preset."""
    scaffold(target=tmp_path, monkeypatch=monkeypatch)

    outcome = package_check(
        path=Path("scenarios") / f"{SCENARIO}.py", name="package data ships prompts and presets"
    )

    assert outcome.passed, outcome.detail


def test_missing_package_data_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without it only .py files are packaged, and the wheel renders nothing."""
    project = scaffold(target=tmp_path, monkeypatch=monkeypatch)
    edit_pyproject(
        project=project, pattern=r"\[tool\.setuptools\.package-data\].*?\n\n", replacement=""
    )

    outcome = package_check(
        path=Path("scenarios") / f"{SCENARIO}.py", name="package data ships prompts and presets"
    )

    assert not outcome.passed
    assert "package-data" in outcome.detail
    assert "'scenarios'" in outcome.detail


def test_a_pattern_that_does_not_reach_a_subdirectory_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`*.jinja` covers prompts beside the module, not prompts inside a folder.

    The mistake the check exists for, and the reason it cannot use `fnmatch`,
    whose `*` crosses separators and would call this covered.
    """
    project = scaffold(target=tmp_path, monkeypatch=monkeypatch)
    edit_pyproject(project=project, pattern=r'"\*\*/\*\.jinja"', replacement='"*.jinja"')

    outcome = package_check(
        path=Path("scenarios") / f"{SCENARIO}.py", name="package data ships prompts and presets"
    )

    assert not outcome.passed
    assert "prompts/" in outcome.detail


def test_package_data_is_not_checked_for_another_build_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reported as a note, because guessing would fail a project that is fine."""
    project = scaffold(target=tmp_path, monkeypatch=monkeypatch)
    edit_pyproject(
        project=project,
        pattern=r'build-backend = "setuptools\.build_meta"',
        replacement='build-backend = "x.y"',
    )

    report = check_scenario_package(loaded=load_one(path=Path("scenarios") / f"{SCENARIO}.py"))

    assert not [one for one in report.outcomes if "package data" in one.check]
    assert any("'x.y'" in note for note in report.notes)


def test_a_project_that_builds_no_wheel_gets_no_package_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a [build-system] nothing is packaged, so there is nothing to check."""
    project = scaffold(target=tmp_path, monkeypatch=monkeypatch)
    edit_pyproject(project=project, pattern=r"\[build-system\].*?\n\n", replacement="")

    report = check_scenario_package(loaded=load_one(path=Path("scenarios") / f"{SCENARIO}.py"))

    assert report.outcomes == []
    assert report.notes == ()


def test_a_path_registering_no_scenario_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing to check, and the error says how to register one."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "plain.py").write_text("VALUE = 1\n")

    with pytest.raises(ScenarioPathError, match="registers no scenario"):
        load_scenarios_from_path(path=Path("plain.py"))


def test_a_file_that_does_not_import_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The import error reaches the author with the file it came from."""
    project = scaffold(target=tmp_path, monkeypatch=monkeypatch)
    module = project / "scenarios" / f"{SCENARIO}.py"
    module.write_text(module.read_text() + "\nraise RuntimeError('broken on purpose')\n")

    with pytest.raises(ScenarioPathError) as raised:
        load_scenarios_from_path(path=Path("scenarios") / f"{SCENARIO}.py")

    assert "broken on purpose" in str(raised.value)
    assert f"{SCENARIO}.py" in str(raised.value)


def test_a_path_that_does_not_exist_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo is reported as one."""
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ScenarioPathError, match="does not exist"):
        load_scenarios_from_path(path=Path("nowhere.py"))
