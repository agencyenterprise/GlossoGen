"""Loading and checking a scenario package that was never installed.

The scaffold is the fixture throughout. It writes a package that passes, so each
test breaks one thing in a copy of it and states what should be reported. That
keeps the tests about the checks rather than about a hand-built tree that may not
resemble what an author actually has.
"""

import inspect
import re
from pathlib import Path

import pytest

from glossogen.scenario_conformance import CheckOutcome, check_scenario, failures
from glossogen.scenario_entry_points import SCENARIO_ENTRY_POINT_GROUP
from glossogen.scenario_loader import find_scenario_class
from glossogen.scenario_package_checks import check_scenario_package
from glossogen.scenario_path_loader import (
    PYPROJECT_NAME,
    ScenarioPathError,
    load_scenario_from_path,
    registered_for_checks,
)
from glossogen.scenario_scaffold import write_scenario_package

REF = "v9.9.9"
SCENARIO = "reactor_purge"


def scaffold(target: Path) -> Path:
    """Write the package every test starts from, and return its directory."""
    return write_scenario_package(
        scenario_name=SCENARIO, target_dir=target, glossogen_ref=REF
    ).package_dir


def edit_pyproject(package_dir: Path, pattern: str, replacement: str) -> None:
    """Rewrite one thing in the generated pyproject."""
    path = package_dir / PYPROJECT_NAME
    path.write_text(re.sub(pattern, replacement, path.read_text(), flags=re.S), encoding="utf-8")


def package_check(package_dir: Path, name: str) -> CheckOutcome:
    """Return the named package check's outcome for this tree."""
    loaded = load_scenario_from_path(package_dir=package_dir)
    report = check_scenario_package(loaded=loaded)
    matching = [outcome for outcome in report.outcomes if outcome.check == name]
    assert matching, f"no check named {name!r} ran; got {[o.check for o in report.outcomes]}"
    return matching[0]


def test_a_scaffolded_package_loads_without_being_installed(tmp_path: Path) -> None:
    """The whole point: no install, no entry-point metadata, still resolved."""
    loaded = load_scenario_from_path(package_dir=scaffold(tmp_path))

    assert loaded.entry_point_name == SCENARIO
    assert loaded.entry_point_group == SCENARIO_ENTRY_POINT_GROUP
    assert loaded.scenario_cls.name() == SCENARIO
    # The distribution spells underscores as hyphens, so these differ.
    assert loaded.module_dir.name == SCENARIO
    assert loaded.package_dir.name == "reactor-purge"


def test_the_contract_checks_pass_on_a_scaffolded_package(tmp_path: Path) -> None:
    """A path-loaded class goes through the same checks as an installed one.

    Registration is what makes the checks that resolve by name agree, so this
    also guards that: without it `the API agrees on primary channels` reports a
    disagreement against a scenario that is fine.
    """
    loaded = load_scenario_from_path(package_dir=scaffold(tmp_path))

    with registered_for_checks(loaded=loaded):
        broken = failures(check_scenario(scenario_cls=loaded.scenario_cls))

    assert not broken, [f"{one.check} — {one.detail}" for one in broken]


def test_registration_is_undone_afterwards(tmp_path: Path) -> None:
    """A command that checks a tree must not change what later lookups resolve."""
    loaded = load_scenario_from_path(package_dir=scaffold(tmp_path))

    with registered_for_checks(loaded=loaded):
        assert find_scenario_class(name=SCENARIO) is loaded.scenario_cls
    assert find_scenario_class(name=SCENARIO) is None


def test_two_trees_of_the_same_name_do_not_return_each_other(tmp_path: Path) -> None:
    """`import` answers from sys.modules before it looks at sys.path.

    So the second tree used to hand back the first tree's class, and every check
    afterwards described a scenario the caller had not named. Nothing about that
    looks wrong: the name matches and the class is real.
    """
    first = load_scenario_from_path(package_dir=scaffold(tmp_path / "a"))
    # Read where each class came from before the next load replaces the module.
    # `inspect.getfile` resolves through `sys.modules`, so afterwards both classes
    # report whichever tree was imported last.
    first_file = Path(inspect.getfile(first.scenario_cls)).resolve()
    second = load_scenario_from_path(package_dir=scaffold(tmp_path / "b"))
    second_file = Path(inspect.getfile(second.scenario_cls)).resolve()

    assert first.scenario_cls is not second.scenario_cls
    assert first.package_dir in first_file.parents
    assert second.package_dir in second_file.parents


def test_a_group_naming_another_contract_version_is_reported(tmp_path: Path) -> None:
    """The version lives in the group, and only one of them is read."""
    package = scaffold(tmp_path)
    edit_pyproject(package, re.escape(SCENARIO_ENTRY_POINT_GROUP), "glossogen.scenarios.v99")

    outcome = package_check(package, "the entry-point group names this contract version")

    assert not outcome.passed
    assert "glossogen.scenarios.v99" in outcome.detail
    assert SCENARIO_ENTRY_POINT_GROUP in outcome.detail


def test_a_group_the_platform_does_not_read_still_loads_the_class(tmp_path: Path) -> None:
    """Reported as a failed check rather than a refusal to load.

    An author wants every problem their scenario has, not the first one. The
    class imports fine; it is the declaration around it that is wrong.
    """
    package = scaffold(tmp_path)
    edit_pyproject(package, re.escape(SCENARIO_ENTRY_POINT_GROUP), "glossogen.scenarios.v99")

    assert load_scenario_from_path(package_dir=package).scenario_cls.name() == SCENARIO


def test_missing_package_data_is_reported(tmp_path: Path) -> None:
    """Without it only .py files are packaged, and the wheel renders nothing."""
    package = scaffold(tmp_path)
    edit_pyproject(package, r"\[tool\.setuptools\.package-data\].*?\n\n", "")

    outcome = package_check(package, "package data ships prompts and presets")

    assert not outcome.passed
    assert "package-data" in outcome.detail


def test_a_pattern_that_does_not_reach_a_subdirectory_is_reported(tmp_path: Path) -> None:
    """`*.jinja` covers prompts beside the module, not prompts inside it.

    The mistake the check exists for, and the reason it cannot use `fnmatch`,
    whose `*` crosses separators and would call this covered.
    """
    package = scaffold(tmp_path)
    edit_pyproject(package, r'"\*\*/\*\.jinja"', '"*.jinja"')

    outcome = package_check(package, "package data ships prompts and presets")

    assert not outcome.passed
    assert "prompts/" in outcome.detail


def test_package_data_is_not_checked_for_another_build_backend(tmp_path: Path) -> None:
    """Reported as a note, because guessing would fail a package that is fine."""
    package = scaffold(tmp_path)
    edit_pyproject(package, r'build-backend = "setuptools\.build_meta"', 'build-backend = "x.y"')

    report = check_scenario_package(loaded=load_scenario_from_path(package_dir=package))

    assert not [one for one in report.outcomes if "package data" in one.check]
    assert any("'x.y'" in note for note in report.notes)


def test_a_non_empty_package_init_is_reported(tmp_path: Path) -> None:
    """Discovery imports it while the event union is still being built."""
    package = scaffold(tmp_path)
    (package / SCENARIO / "__init__.py").write_text(
        f"from {SCENARIO}.scenario import ReactorPurgeScenario\n", encoding="utf-8"
    )

    outcome = package_check(package, "the package __init__ is empty")

    assert not outcome.passed


def test_a_name_a_built_in_holds_is_reported(tmp_path: Path) -> None:
    """The blind spot `check-scenario` cannot see: it reports the built-in as healthy."""
    package = scaffold(tmp_path)
    renamed = package / "veyru"
    (package / SCENARIO).rename(renamed)
    for path in [*renamed.rglob("*.py"), package / PYPROJECT_NAME]:
        path.write_text(
            path.read_text().replace(SCENARIO, "veyru").replace("ReactorPurge", "Veyru"),
            encoding="utf-8",
        )

    outcome = package_check(package, "the name is not already taken")

    assert not outcome.passed
    assert "glossogen.scenarios.veyru" in outcome.detail


def test_a_tree_holding_the_scenario_it_declares_is_not_a_collision(tmp_path: Path) -> None:
    """The ordinary case is a tree already installed as editable.

    That resolves the name to the author's own class, which is agreement. Compared
    by where the class is defined rather than by name, so this passes.
    """
    package = scaffold(tmp_path)
    loaded = load_scenario_from_path(package_dir=package)

    with registered_for_checks(loaded=loaded):
        outcome = [
            one
            for one in check_scenario_package(loaded=loaded).outcomes
            if one.check == "the name is not already taken"
        ][0]

    assert outcome.passed


def test_a_directory_with_no_pyproject_says_what_to_point_at(tmp_path: Path) -> None:
    """The likely mistake is naming the module rather than the distribution."""
    package = scaffold(tmp_path)

    with pytest.raises(ScenarioPathError) as raised:
        load_scenario_from_path(package_dir=package / SCENARIO)

    assert PYPROJECT_NAME in str(raised.value)


def test_a_tree_declaring_no_scenario_is_refused(tmp_path: Path) -> None:
    """Nothing to check, and the error names the group to declare it under."""
    package = scaffold(tmp_path)
    edit_pyproject(package, r"\[project\.entry-points[^\]]*\][^\[]*", "")

    with pytest.raises(ScenarioPathError) as raised:
        load_scenario_from_path(package_dir=package)

    assert SCENARIO_ENTRY_POINT_GROUP in str(raised.value)


def test_the_unversioned_group_is_named_in_the_error(tmp_path: Path) -> None:
    """One character from correct, and nothing reads it."""
    package = scaffold(tmp_path)
    edit_pyproject(package, re.escape(SCENARIO_ENTRY_POINT_GROUP), "glossogen.scenarios")

    with pytest.raises(ScenarioPathError) as raised:
        load_scenario_from_path(package_dir=package)

    assert "glossogen.scenarios" in str(raised.value)
    assert SCENARIO_ENTRY_POINT_GROUP in str(raised.value)


def test_a_value_that_does_not_import_says_so(tmp_path: Path) -> None:
    """The declaration is checked against the class it names, not just parsed."""
    package = scaffold(tmp_path)
    edit_pyproject(package, r"scenario:ReactorPurgeScenario", "scenario:NoSuchClass")

    with pytest.raises(ScenarioPathError) as raised:
        load_scenario_from_path(package_dir=package)

    assert "does not import" in str(raised.value)


def test_a_key_that_disagrees_with_the_reported_name_is_refused(tmp_path: Path) -> None:
    """Runs are stored under name(), and every later command looks them up by key."""
    package = scaffold(tmp_path)
    edit_pyproject(package, rf"\n{SCENARIO} = ", "\npurge = ")

    with pytest.raises(ScenarioPathError) as raised:
        load_scenario_from_path(package_dir=package)

    assert "calls itself" in str(raised.value)
