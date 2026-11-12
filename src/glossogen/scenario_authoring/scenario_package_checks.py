"""Checks on the project around a scenario loaded from a path.

:mod:`glossogen.scenario_authoring.scenario_conformance` checks a built scenario,
which says nothing about how the project around it is packaged. A project whose
``pyproject.toml`` builds a wheel has to ship the prompts and presets as package
data: one that omits them installs a wheel that renders nothing, while the source
tree the author tests against works fine.

A check that cannot be evaluated returns a note rather than a verdict, because a
false failure teaches a reader to skip the output.
"""

import logging
import re
from pathlib import Path
from typing import Any, NamedTuple, cast

from glossogen.scenario_authoring.scenario_conformance import CheckOutcome
from glossogen.scenario_contract.path_loader import PathLoadedScenario, table_at

logger = logging.getLogger(__name__)

SETUPTOOLS_BACKEND = "setuptools.build_meta"
MANIFEST_NAME = "MANIFEST.in"

# Build requirements that add files to a distribution by finding them rather than
# by being told about them, so their presence means a pattern here is not the only
# thing that could be shipping the data.
_FILE_FINDER_PLUGINS = frozenset({"setuptools-scm", "setuptools-git-versioning"})

# What has to reach the wheel for a scenario to work once installed: the prompt
# templates it renders, and the knobs presets `--config` resolves by name.
_REQUIRED_DATA_SUFFIXES = (".jinja", ".json")

# How many uncovered files to name before summarising the rest. Naming one is
# usually enough to see the pattern, and naming all of them buries the other
# checks in a wall of paths.
_NAMED_UNCOVERED_LIMIT = 3


class PackageCheckReport(NamedTuple):
    """Verdicts on the package, plus what could not be checked and why."""

    outcomes: list[CheckOutcome]
    notes: tuple[str, ...]


def check_scenario_package(loaded: PathLoadedScenario) -> PackageCheckReport:
    """Run the package checks against a scenario loaded from a path.

    Nothing is checked when the project has no ``pyproject.toml`` with a
    ``[build-system]`` table, since nothing builds a wheel from it.
    """
    if loaded.pyproject is None or not table_at(document=loaded.pyproject, path=("build-system",)):
        return PackageCheckReport(outcomes=[], notes=())
    return _package_data_ships_prompts_and_presets(loaded=loaded, pyproject=loaded.pyproject)


def _package_data_ships_prompts_and_presets(
    loaded: PathLoadedScenario, pyproject: dict[str, Any]
) -> PackageCheckReport:
    """Every prompt and preset on disk is covered by a declared data pattern.

    Checked against the files that are actually there rather than against the
    patterns alone, because the patterns are only wrong relative to a layout:
    ``*.jinja`` is correct for prompts beside the module and wrong for prompts in
    a subdirectory of it, and nothing about the string says which.

    Only setuptools is read. Another backend declares its data somewhere this does
    not know how to look, and guessing would either pass everything or fail a
    package that is fine, so it returns a note instead.

    ``package-data`` is also not the only way to ship data under setuptools.
    ``include-package-data`` defaults to true for a pyproject-configured build, so a
    ``MANIFEST.in`` or a file-finder plugin such as setuptools-scm supplies the same
    files without a pattern here. Where one of those could be doing the work, an
    uncovered file is a note rather than a failure: this reads the tree and cannot
    see what a build would resolve, and failing a distribution that ships correctly
    is worse than not checking it.
    """
    check = "package data ships prompts and presets"
    backend = table_at(document=pyproject, path=("build-system",)).get("build-backend")
    if backend != SETUPTOOLS_BACKEND:
        return PackageCheckReport(
            outcomes=[],
            notes=(
                f"Not checked: {check}. The build backend is {backend!r}, and only "
                f"{SETUPTOOLS_BACKEND!r} is read. Confirm by hand that a built wheel "
                "carries the prompt templates and the knobs presets.",
            ),
        )

    shipped = _files_needing_packaging(module_dir=loaded.module_dir)
    if not shipped:
        return PackageCheckReport(outcomes=[], notes=())

    patterns = _declared_data_patterns(loaded=loaded, pyproject=pyproject)
    matchers = [_pattern_to_regex(pattern=pattern) for pattern in patterns]
    uncovered = [
        relative for relative in shipped if not any(matcher.match(relative) for matcher in matchers)
    ]
    if uncovered:
        supplier = _other_data_supplier(loaded=loaded, pyproject=pyproject)
        if supplier is not None:
            return PackageCheckReport(
                outcomes=[],
                notes=(
                    f"Not checked: {check}. No declared pattern covers "
                    f"{_summarise(paths=uncovered)}, but {supplier} can supply the same "
                    "files and this reads the tree rather than a build. Confirm a built "
                    "wheel carries the prompt templates and the knobs presets.",
                ),
            )
        if not patterns:
            return PackageCheckReport(
                outcomes=[
                    CheckOutcome(
                        check=check,
                        preset="",
                        passed=False,
                        detail=(
                            f"[tool.setuptools.package-data] declares nothing for "
                            f"{loaded.package_name!r}, and nothing else here ships data "
                            f"either, so only .py files are packaged and a built wheel "
                            f"renders no prompt ({len(shipped)} file(s) affected)"
                        ),
                    )
                ],
                notes=(),
            )
    if not uncovered:
        return PackageCheckReport(
            outcomes=[CheckOutcome(check=check, preset="", passed=True, detail="")], notes=()
        )
    return PackageCheckReport(
        outcomes=[
            CheckOutcome(
                check=check,
                preset="",
                passed=False,
                detail=(
                    f"no declared pattern covers {_summarise(paths=uncovered)}. Declared: "
                    f"{sorted(patterns)}"
                ),
            )
        ],
        notes=(),
    )


def _other_data_supplier(loaded: PathLoadedScenario, pyproject: dict[str, Any]) -> str | None:
    """Name the other thing that could be shipping this tree's data, if any.

    ``include-package-data`` set false rules them all out, leaving ``package-data``
    as the only route and an uncovered file a real failure. Otherwise a
    ``MANIFEST.in`` beside the pyproject, or a file-finder plugin among the build
    requirements, supplies files without naming a pattern.
    """
    setuptools_table = table_at(document=pyproject, path=("tool", "setuptools"))
    if setuptools_table.get("include-package-data") is False:
        return None

    if (loaded.project_dir / MANIFEST_NAME).is_file():
        return MANIFEST_NAME

    requires = table_at(document=pyproject, path=("build-system",)).get("requires")
    if isinstance(requires, list):
        for requirement in cast(list[object], requires):
            if not isinstance(requirement, str):
                continue
            name = re.split(r"[<>=!\[~; ]", requirement, maxsplit=1)[0].strip().lower()
            if name.replace("_", "-") in _FILE_FINDER_PLUGINS:
                return f"the {name} build requirement"
    return None


def _files_needing_packaging(module_dir: Path) -> list[str]:
    """Return every prompt and preset under the module, relative and posix-formed."""
    found: list[str] = []
    for path in sorted(module_dir.rglob("*")):
        if not path.is_file() or path.suffix not in _REQUIRED_DATA_SUFFIXES:
            continue
        found.append(path.relative_to(module_dir).as_posix())
    return found


def _declared_data_patterns(loaded: PathLoadedScenario, pyproject: dict[str, Any]) -> set[str]:
    """Return the data patterns declared for the scenario's package, including ``*``."""
    declared = table_at(document=pyproject, path=("tool", "setuptools", "package-data"))
    patterns: set[str] = set()
    for key in (loaded.package_name, "*"):
        entry = declared.get(key)
        if not isinstance(entry, list):
            continue
        items = cast(list[object], entry)
        patterns.update(item for item in items if isinstance(item, str))
    return patterns


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile one setuptools data pattern.

    ``fnmatch`` is not usable here: its ``*`` crosses directory separators, so
    ``*.jinja`` would be reported as covering ``prompts/system.jinja``, which is
    the exact mistake this check exists to catch.
    """
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.compile(f"^{''.join(parts)}$")


def _summarise(paths: list[str]) -> str:
    """Name the first few paths, then count the rest."""
    named = ", ".join(paths[:_NAMED_UNCOVERED_LIMIT])
    remaining = len(paths) - _NAMED_UNCOVERED_LIMIT
    if remaining <= 0:
        return named
    return f"{named} and {remaining} more"
