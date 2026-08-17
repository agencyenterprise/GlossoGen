"""Checks on a scenario's package that only mean something before it is installed.

:mod:`glossogen.scenario_conformance` checks a built scenario, which says nothing
about the distribution around it. These are the other half, and every one of them
is a failure that installation either hides or converts into something harder to
read:

``package-data`` that omits the prompts installs a wheel that renders nothing,
while the editable install the author is testing against works fine. An
entry-point group naming another contract version is not read at all, so the
scenario is simply missing from the list. A non-empty ``__init__`` breaks event
discovery, which runs while the event union is mid-import. A name a built-in
already holds stays with the built-in, and the collision is only logged, so
validating by name afterwards reports a healthy scenario: somebody else's.

A check that cannot be evaluated returns a note rather than a verdict. The
alternative is a false failure, which is what makes people stop reading output.
"""

import inspect
import logging
import re
from pathlib import Path
from typing import NamedTuple, cast

from glossogen.scenario_conformance import CheckOutcome
from glossogen.scenario_entry_points import SCENARIO_ENTRY_POINT_GROUP
from glossogen.scenario_loader import find_scenario_class
from glossogen.scenario_path_loader import (
    PathLoadedScenario,
    declared_contract_version,
    platform_contract_version,
    table_at,
)

logger = logging.getLogger(__name__)

SETUPTOOLS_BACKEND = "setuptools.build_meta"

# What has to reach the wheel for a scenario to work once installed: the prompt
# templates it renders, and the presets that are the only way to launch it.
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
    """Run every package-level check against a tree already loaded from a path."""
    outcomes = [
        _group_names_this_contract_version(loaded=loaded),
        _package_init_is_empty(loaded=loaded),
        _the_name_is_not_taken(loaded=loaded),
    ]
    data = _package_data_ships_prompts_and_presets(loaded=loaded)
    outcomes.extend(data.outcomes)
    return PackageCheckReport(outcomes=outcomes, notes=data.notes)


def _group_names_this_contract_version(loaded: PathLoadedScenario) -> CheckOutcome:
    """The group carries the contract version, and only one of them is read."""
    check = "the entry-point group names this contract version"
    declared = declared_contract_version(group=loaded.entry_point_group)
    running = platform_contract_version()
    if declared == running:
        return CheckOutcome(check=check, preset="", passed=True, detail="")
    return CheckOutcome(
        check=check,
        preset="",
        passed=False,
        detail=(
            f"declared under {loaded.entry_point_group!r}, which this glossogen does not "
            f"read; it reads {SCENARIO_ENTRY_POINT_GROUP!r}. Upgrade whichever side is "
            "older, or correct the group name"
        ),
    )


def _package_init_is_empty(loaded: PathLoadedScenario) -> CheckOutcome:
    """Event discovery imports this while the event union is still being built."""
    check = "the package __init__ is empty"
    init = loaded.module_dir / "__init__.py"
    if not init.is_file():
        return CheckOutcome(
            check=check,
            preset="",
            passed=False,
            detail=f"{init} does not exist, so {loaded.module_dir.name} is not a package",
        )
    body = init.read_text(encoding="utf-8").strip()
    if body == "":
        return CheckOutcome(check=check, preset="", passed=True, detail="")
    return CheckOutcome(
        check=check,
        preset="",
        passed=False,
        detail=(
            f"{init} is not empty. Discovery imports it while the event union is "
            "mid-import, so anything it pulls in closes that cycle"
        ),
    )


def _the_name_is_not_taken(loaded: PathLoadedScenario) -> CheckOutcome:
    """A name already claimed stays with whoever claimed it, and only logs.

    Compared by where the resolved class is defined rather than by name alone,
    because the ordinary case is an author checking a tree they have already
    installed as editable. That resolves to their own class, which is agreement
    rather than collision.
    """
    check = "the name is not already taken"
    existing = find_scenario_class(name=loaded.entry_point_name)
    if existing is None:
        return CheckOutcome(check=check, preset="", passed=True, detail="")
    if _is_defined_under(cls_module_file=_defining_file(cls=existing), root=loaded.package_dir):
        return CheckOutcome(check=check, preset="", passed=True, detail="")
    return CheckOutcome(
        check=check,
        preset="",
        passed=False,
        detail=(
            f"{loaded.entry_point_name!r} already resolves to "
            f"{existing.__module__}.{existing.__name__}, which is not in this tree. A name "
            "already taken stays with the scenario that holds it, so this package would "
            "install and never resolve. Pick another name"
        ),
    )


def _defining_file(cls: type) -> Path | None:
    """Return the file a class is defined in, or None when that cannot be read.

    Resolved through ``sys.modules``, so this answers for whichever tree of a
    given package name was imported most recently. That holds for a command which
    loads one tree and exits; a caller loading several would have to read this
    before the next load rather than afterwards.
    """
    try:
        return Path(inspect.getfile(cls)).resolve()
    except (TypeError, OSError):
        logger.exception("Could not locate the file defining %r", cls)
        return None


def _is_defined_under(cls_module_file: Path | None, root: Path) -> bool:
    """Whether a class's defining file lives inside ``root``."""
    if cls_module_file is None:
        return False
    return root in cls_module_file.parents


def _package_data_ships_prompts_and_presets(loaded: PathLoadedScenario) -> PackageCheckReport:
    """Every prompt and preset on disk is covered by a declared data pattern.

    Checked against the files that are actually there rather than against the
    patterns alone, because the patterns are only wrong relative to a layout:
    ``*.jinja`` is correct for prompts beside the module and wrong for prompts in
    a subdirectory of it, and nothing about the string says which.

    Only setuptools is read. Another backend declares its data somewhere this does
    not know how to look, and guessing would either pass everything or fail a
    package that is fine, so it returns a note instead.
    """
    check = "package data ships prompts and presets"
    backend = table_at(document=loaded.pyproject, path=("build-system",)).get("build-backend")
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

    patterns = _declared_data_patterns(loaded=loaded)
    if not patterns:
        return PackageCheckReport(
            outcomes=[
                CheckOutcome(
                    check=check,
                    preset="",
                    passed=False,
                    detail=(
                        f"[tool.setuptools.package-data] declares nothing for "
                        f"{loaded.module_dir.name!r}, so only .py files are packaged and a "
                        f"built wheel renders no prompt ({len(shipped)} file(s) affected)"
                    ),
                )
            ],
            notes=(),
        )

    matchers = [_pattern_to_regex(pattern=pattern) for pattern in patterns]
    uncovered = [
        relative for relative in shipped if not any(matcher.match(relative) for matcher in matchers)
    ]
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


def _files_needing_packaging(module_dir: Path) -> list[str]:
    """Return every prompt and preset under the module, relative and posix-formed."""
    found: list[str] = []
    for path in sorted(module_dir.rglob("*")):
        if not path.is_file() or path.suffix not in _REQUIRED_DATA_SUFFIXES:
            continue
        found.append(path.relative_to(module_dir).as_posix())
    return found


def _declared_data_patterns(loaded: PathLoadedScenario) -> set[str]:
    """Return the data patterns declared for this module, including the ``*`` key."""
    declared = table_at(document=loaded.pyproject, path=("tool", "setuptools", "package-data"))
    patterns: set[str] = set()
    for key in (loaded.module_dir.name, "*"):
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
