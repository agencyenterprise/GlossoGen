"""`glossogen validate`, from the argument through to the exit code.

The checks behind this command are covered elsewhere. What is covered here is the
command: that a name and a path both resolve, that the two forms cannot be
confused for each other, that a failure exits non-zero rather than reporting and
carrying on, and that a check which could not be evaluated prints a note instead
of a verdict.

Driven through `main` with a patched `sys.argv`, because the argument parsing and
the exit code are the parts being checked, and neither exists below it.
"""

import re
import shutil
from pathlib import Path

import pytest

from glossogen.cli.cli_entry import main
from tests.fakes.packaged_scenario_project import write_packaged_project

SCENARIO = "reactor_purge"
SCENARIO_FILE = f"scenarios/{SCENARIO}/{SCENARIO}.py"


@pytest.fixture(autouse=True)
def isolated(isolated_scenario_imports: None) -> None:
    """`main` loads a catalog of its own, and the packaged project's modules are imported."""
    _ = isolated_scenario_imports


def enter_packaged_project(target: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write a project that passes, enter it, and return its directory."""
    project = write_packaged_project(target=target, scenario_name=SCENARIO)
    monkeypatch.chdir(project)
    return project


def validate(target: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run `glossogen validate <target>`.

    Returns on success and raises `SystemExit` on failure, which is what the CLI
    does: a zero exit is the absence of a raise rather than `SystemExit(0)`.
    """
    monkeypatch.setattr("sys.argv", ["glossogen", "validate", target])
    main()


def edit_pyproject(package_dir: Path, pattern: str, replacement: str) -> None:
    """Rewrite one thing in the packaged project's pyproject."""
    path = package_dir / "pyproject.toml"
    path.write_text(re.sub(pattern, replacement, path.read_text(), flags=re.S), encoding="utf-8")


def test_a_name_passes_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The form CI uses, against a scenario that ships here."""
    validate(target="prisoners_dilemma", monkeypatch=monkeypatch)

    out = capsys.readouterr().out
    assert "prisoners_dilemma:" in out
    assert "checks passed" in out


def test_a_scenario_file_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The form an author uses while writing, and the reason the command takes a path.

    The report names the path as well as the scenario, since the two can disagree.
    """
    enter_packaged_project(target=tmp_path, monkeypatch=monkeypatch)

    validate(target=SCENARIO_FILE, monkeypatch=monkeypatch)

    out = capsys.readouterr().out
    assert f"{SCENARIO} ({SCENARIO_FILE})" in out
    assert "checks passed" in out


def test_a_path_runs_more_checks_than_a_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The package checks only exist for the path form, so the counts differ.

    Asserted as a comparison rather than against a number, which would be a lie the
    next time a check is added.
    """
    enter_packaged_project(target=tmp_path, monkeypatch=monkeypatch)

    def count(target: str) -> int:
        validate(target=target, monkeypatch=monkeypatch)
        found = re.search(r"(\d+) checks passed", capsys.readouterr().out)
        assert found is not None
        return int(found.group(1))

    assert count(target=SCENARIO_FILE) > count(target=SCENARIO)


def test_a_failing_project_exits_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reporting a failure and exiting zero would make this useless in CI."""
    project = enter_packaged_project(target=tmp_path, monkeypatch=monkeypatch)
    edit_pyproject(
        package_dir=project, pattern=r"\[tool\.setuptools\.package-data\].*?\n\n", replacement=""
    )

    with pytest.raises(SystemExit) as raised:
        validate(target=SCENARIO_FILE, monkeypatch=monkeypatch)

    assert raised.value.code == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "checks failed" in out


def test_a_check_that_could_not_be_evaluated_prints_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A note, not a failure. Failing a project that is fine is what stops people reading output."""
    project = enter_packaged_project(target=tmp_path, monkeypatch=monkeypatch)
    edit_pyproject(
        package_dir=project,
        pattern=r'build-backend = "setuptools\.build_meta"',
        replacement='build-backend = "x.y"',
    )

    validate(target=SCENARIO_FILE, monkeypatch=monkeypatch)

    out = capsys.readouterr().out
    assert "NOTE" in out
    assert "FAIL" not in out


def test_an_unknown_name_says_what_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo is the likely cause, so the message carries the real names."""
    with pytest.raises(SystemExit) as raised:
        validate(target="veyroo", monkeypatch=monkeypatch)

    assert "veyru" in str(raised.value.code)


def test_a_string_that_can_be_neither_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Holding a separator, it cannot be a name; not existing, it cannot be a path."""
    with pytest.raises(SystemExit) as raised:
        validate(target="./no/such/place", monkeypatch=monkeypatch)

    message = str(raised.value.code)
    assert "does not exist" in message
    assert "lowercase identifier" in message


def test_a_name_that_is_also_a_directory_resolves_to_the_loaded_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one string that could read as either, and it says which it chose.

    Resolving to the loaded scenario is the common reading; the note points at
    the other one, which is a `./` away.
    """
    (tmp_path / "prisoners_dilemma").mkdir()
    monkeypatch.chdir(tmp_path)

    validate(target="prisoners_dilemma", monkeypatch=monkeypatch)

    out = capsys.readouterr().out
    assert "NOTE" in out
    assert "./prisoners_dilemma" in out


def test_a_nested_scenarios_events_are_not_reported_as_this_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A scenario folder inside another's package is a package the first one imports from.

    The configured folder holds both scenarios, and the outer one imports a
    constant from the inner one. The inner scenario's event class lives under the
    outer scenario's package, so it is the other registered scenario's declared
    events that keep it from being reported against the outer one.
    """
    project = enter_packaged_project(target=tmp_path, monkeypatch=monkeypatch)
    inner_dir = copy_scenario_folder(project=project, new_name="second_drill")
    nested_dir = project / "scenarios" / SCENARIO / "second_drill"
    shutil.move(src=inner_dir, dst=nested_dir)
    outer_module = project / "scenarios" / SCENARIO / f"{SCENARIO}.py"
    outer_module.write_text(
        outer_module.read_text()
        + (
            f"\nfrom scenarios.{SCENARIO}.second_drill.second_drill "
            "import BRIEFER_ID as INNER_BRIEFER_ID\n"
        )
    )
    edit_pyproject(
        package_dir=project,
        pattern=r'scenarios = \["scenarios"\]',
        replacement=f'scenarios = ["scenarios/{SCENARIO}"]',
    )

    validate(target=f"scenarios/{SCENARIO}", monkeypatch=monkeypatch)

    out = capsys.readouterr().out
    assert f"{SCENARIO} (scenarios/{SCENARIO})" in out
    assert "checks passed" in out


def test_two_scenarios_in_one_folder_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """They would read each other's presets and prompts, so loading them fails.

    The message names both scenarios, their modules and the folder, and says how
    to fix it.
    """
    project = enter_packaged_project(target=tmp_path, monkeypatch=monkeypatch)
    folder = project / "scenarios" / SCENARIO
    first = (folder / f"{SCENARIO}.py").read_text()
    (folder / "second_drill.py").write_text(
        first.replace(SCENARIO, "second_drill").replace("ReactorPurge", "SecondDrill")
    )
    edit_pyproject(
        package_dir=project, pattern=r'scenarios = \["scenarios"\]', replacement="scenarios = []"
    )

    with pytest.raises(SystemExit) as raised:
        validate(target=f"scenarios/{SCENARIO}", monkeypatch=monkeypatch)

    message = str(raised.value.code)
    assert "'reactor_purge'" in message
    assert "'second_drill'" in message
    assert f"scenarios.{SCENARIO}.{SCENARIO}" in message
    assert f"scenarios.{SCENARIO}.second_drill" in message
    assert str(folder.resolve()) in message
    assert "its own folder" in message


def copy_scenario_folder(project: Path, new_name: str) -> Path:
    """Copy the project's scenario folder as a second scenario called ``new_name``."""
    source = project / "scenarios" / SCENARIO
    target = project / "scenarios" / new_name
    shutil.copytree(src=source, dst=target)
    module = target / f"{SCENARIO}.py"
    module.rename(target / f"{new_name}.py")
    renamed = target / f"{new_name}.py"
    renamed.write_text(
        renamed.read_text().replace(SCENARIO, new_name).replace("ReactorPurge", "SecondDrill")
    )
    return target
