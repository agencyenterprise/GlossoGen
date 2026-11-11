"""Every top-level module is covered by the contracts that list modules by name.

Contracts B, F and G name their source modules explicitly. A module added later
and left off the list would escape them without any config changing, so this test
fails until the new module is either listed or named as an exemption here.
"""

import ast
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "src" / "glossogen"

# Contract letter -> top-level modules the contract exempts on purpose.
EXEMPT_SOURCES = {
    "B": {"server"},
    "F": {"scenarios", "scenario_registry", "testing"},
    "G": {"cli", "__main__"},
}


def top_level_modules() -> set[str]:
    """Return the names of the modules and packages directly under glossogen."""
    names: set[str] = set()
    for entry in PACKAGE_ROOT.iterdir():
        if entry.name == "__pycache__" or entry.name == "__init__.py":
            continue
        if entry.is_dir():
            names.add(entry.name)
        elif entry.suffix == ".py":
            names.add(entry.stem)
    return names


def contract_sources(letter: str) -> set[str]:
    """Return the top-level names a contract lists as source modules."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contracts = pyproject["tool"]["importlinter"]["contracts"]
    for contract in contracts:
        if contract["name"].startswith(f"{letter}. "):
            return {module.removeprefix("glossogen.") for module in contract["source_modules"]}
    raise AssertionError(f"no contract {letter}")


@pytest.mark.parametrize("letter", sorted(EXEMPT_SOURCES))
def test_every_top_level_module_is_a_source_or_an_exemption(letter: str) -> None:
    uncovered = top_level_modules() - contract_sources(letter=letter) - EXEMPT_SOURCES[letter]

    assert uncovered == set(), f"contract {letter} does not cover {sorted(uncovered)}"


@pytest.mark.parametrize("letter", sorted(EXEMPT_SOURCES))
def test_a_contract_lists_no_module_that_does_not_exist(letter: str) -> None:
    stale = contract_sources(letter=letter) - top_level_modules()

    assert stale == set(), f"contract {letter} lists missing modules {sorted(stale)}"


def test_the_root_package_initializer_imports_nothing() -> None:
    tree = ast.parse((PACKAGE_ROOT / "__init__.py").read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]

    assert imports == []
