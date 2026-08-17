"""`glossogen validate`, from the argument through to the exit code.

The checks behind this command are covered elsewhere. What is covered here is the
command: that a name and a directory both resolve, that the two forms cannot be
confused for each other, that a failure exits non-zero rather than reporting and
carrying on, and that a check which could not be evaluated prints a note instead
of a verdict.

Driven through `main` with a patched `sys.argv`, because the argument parsing and
the exit code are the parts being checked, and neither exists below it.
"""

import re
from importlib.metadata import EntryPoint
from pathlib import Path

import pytest

from glossogen.cli import main
from glossogen.scenario_entry_points import SCENARIO_ENTRY_POINT_GROUP
from glossogen.scenario_scaffold import write_scenario_package
from tests.fakes.installed_entry_points import declare_in_groups

SCENARIO = "reactor_purge"
REF = "v9.9.9"


def scaffold(target: Path) -> Path:
    """Write a package that passes, for a test to break one thing in."""
    return write_scenario_package(
        scenario_name=SCENARIO, target_dir=target, glossogen_ref=REF
    ).package_dir


def validate(target: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run `glossogen validate <target>`.

    Returns on success and raises `SystemExit` on failure, which is what the CLI
    does: a zero exit is the absence of a raise rather than `SystemExit(0)`.
    """
    monkeypatch.setattr("sys.argv", ["glossogen", "validate", target])
    main()


def edit_pyproject(package_dir: Path, pattern: str, replacement: str) -> None:
    """Rewrite one thing in a generated pyproject."""
    path = package_dir / "pyproject.toml"
    path.write_text(re.sub(pattern, replacement, path.read_text(), flags=re.S), encoding="utf-8")


def test_a_name_passes_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The form CI uses, against a scenario that ships here."""
    validate("prisoners_dilemma", monkeypatch)

    out = capsys.readouterr().out
    assert "prisoners_dilemma:" in out
    assert "checks passed" in out


def test_a_directory_passes_without_the_package_being_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The form an author uses while writing, and the reason the command takes one."""
    package = scaffold(tmp_path)

    validate(str(package), monkeypatch)

    assert f"{SCENARIO}: " in capsys.readouterr().out


def test_a_directory_runs_more_checks_than_a_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The package checks only exist for the directory form, so the counts differ.

    Asserted as a comparison rather than against a number, which would be a lie the
    next time a check is added.
    """

    def count(target: str) -> int:
        validate(target, monkeypatch)
        found = re.search(r"(\d+) checks passed", capsys.readouterr().out)
        assert found is not None
        return int(found.group(1))

    by_name = count("prisoners_dilemma")
    by_directory = count(str(scaffold(tmp_path)))

    assert by_directory > by_name


def test_a_failing_package_exits_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reporting a failure and exiting zero would make this useless in CI."""
    package = scaffold(tmp_path)
    (package / SCENARIO / "__init__.py").write_text("BROKEN = True\n", encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        validate(str(package), monkeypatch)

    assert raised.value.code == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "checks failed" in out


def test_a_check_that_could_not_be_evaluated_prints_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A note, not a failure. Failing a package that is fine is what stops people reading output."""
    package = scaffold(tmp_path)
    edit_pyproject(package, r'build-backend = "setuptools\.build_meta"', 'build-backend = "x.y"')

    validate(str(package), monkeypatch)

    out = capsys.readouterr().out
    assert "NOTE" in out
    assert "FAIL" not in out


def test_an_unknown_name_says_what_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo is the likely cause, so the message carries the real names."""
    with pytest.raises(SystemExit) as raised:
        validate("veyroo", monkeypatch)

    assert "veyru" in str(raised.value.code)


def test_a_string_that_can_be_neither_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Holding a separator, it cannot be a name; not existing, it cannot be a path."""
    with pytest.raises(SystemExit) as raised:
        validate("./no/such/place", monkeypatch)

    message = str(raised.value.code)
    assert "not a directory" in message
    assert "lowercase identifier" in message


def test_a_directory_that_is_not_a_package_says_what_to_point_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The likely mistake is naming the module rather than the distribution."""
    package = scaffold(tmp_path)

    with pytest.raises(SystemExit) as raised:
        validate(str(package / SCENARIO), monkeypatch)

    assert "pyproject.toml" in str(raised.value.code)


def test_a_name_that_is_also_a_directory_resolves_to_the_installed_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one string that could read as either, and it says which it chose.

    Resolving to the installed scenario is the common reading; the note points at
    the other one, which is a `./` away.
    """
    (tmp_path / "prisoners_dilemma").mkdir()
    monkeypatch.chdir(tmp_path)

    validate("prisoners_dilemma", monkeypatch)

    out = capsys.readouterr().out
    assert "NOTE" in out
    assert "./prisoners_dilemma" in out


def test_a_scenario_that_is_installed_but_cannot_load_says_why(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not "unknown scenario", which is what the soft loader would have made it.

    `find_scenario_class` answers None both for a name nothing declares and for one
    that is declared and fails to import. Resolving through it reported the second
    as the first, in a message that then listed the very name it called unknown.
    The name being declared is decided from installed metadata, which imports
    nothing, so a failure to import is reported as one.
    """
    declare_in_groups(
        monkeypatch,
        {
            SCENARIO_ENTRY_POINT_GROUP: [
                EntryPoint(
                    name="explodes",
                    value="tests.fakes.scenario_with_broken_events.events:Anything",
                    group=SCENARIO_ENTRY_POINT_GROUP,
                )
            ]
        },
    )

    with pytest.raises(SystemExit) as raised:
        validate("explodes", monkeypatch)

    message = str(raised.value.code)
    assert "Unknown scenario" not in message
    assert "explodes" in message
