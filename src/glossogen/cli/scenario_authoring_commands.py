"""The ``validate`` and ``new-scenario`` subcommands."""

import argparse
import importlib.util
import json
import logging
import os
import shlex
import sys
import tomllib
from importlib import metadata
from pathlib import Path

from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.scenario_authoring.scenario_conformance import CheckOutcome, check_scenario, failures
from glossogen.scenario_authoring.scenario_package_checks import check_scenario_package
from glossogen.scenario_authoring.scenario_scaffold import (
    ScaffoldError,
    configured_sources,
    sources_reach,
    write_scenario_folder,
)
from glossogen.scenario_authoring.scenario_target import (
    CheckTarget,
    ScenarioPathError,
    resolve_check_targets,
)
from glossogen.scenario_contract.catalog import current_scenario_catalog
from glossogen.scenario_contract.scenario_sources import (
    SCENARIOS_ENV_VAR,
    ProjectLocation,
    find_project,
)

logger = logging.getLogger(__name__)

GLOSSOGEN_REPOSITORY = "git+https://github.com/agencyenterprise/GlossoGen.git"

# The model the printed smoke run uses: the cheapest Anthropic model, which is
# also the canonical judge.
SMOKE_RUN_MODEL = "claude-haiku-4-5-20251001"


def add_validate_parser(subparsers: SubcommandParsers, scenario_names: list[str]) -> None:
    """Add the ``validate`` subcommand and its flags."""
    validate_parser = subparsers.add_parser(
        "validate",
        help="Check a scenario against the contract, without launching it",
    )
    validate_parser.add_argument(
        "target",
        type=str,
        help=(
            "A loaded scenario's name, or a .py file or directory that registers "
            "scenarios with @scenario, which is then loaded as one more source. "
            f"Loaded: {', '.join(scenario_names)}"
        ),
    )


def add_new_scenario_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``new-scenario`` subcommand and its flags."""
    new_scenario_parser = subparsers.add_parser(
        "new-scenario",
        help=(
            "Write a runnable scenario folder, <target-dir>/<scenario_name>/, with "
            "its module, knobs preset, prompts and a test. Nothing else in the "
            "project is written or changed"
        ),
    )
    new_scenario_parser.add_argument(
        "scenario_name",
        type=str,
        help=(
            "Name of the scenario to create. Becomes the folder, the module, the "
            "name given to @scenario and the run directory, so it has to be a "
            "lowercase identifier"
        ),
    )
    new_scenario_parser.add_argument(
        "--target-dir",
        type=str,
        default=".",
        help=(
            "Directory to create the scenario folder in, as <target-dir>/<scenario_name>/. "
            "Defaults to the working directory"
        ),
    )


def handle_validate(args: argparse.Namespace) -> None:
    """Check scenarios against the contract and report everything that failed.

    Takes a name or a path. Which one it was decides only how the classes are
    found: the contract checks are the same either way. A path checks every
    scenario it registers, and also gets the package checks, which are about the
    project around it.

    Exits non-zero when anything failed, so this works as a CI step in whichever
    project ships the scenario.

    Needs no API key, and checks no model's reachability: describing a scenario
    must not require a credential, and a launch checks what it can reach where the
    run's own model and provider are known.
    """
    try:
        targets = resolve_check_targets(target=args.target)
    except (ScenarioPathError, ValueError) as refusal:
        raise SystemExit(f"FAIL {args.target}: {refusal}") from refusal

    failed_any = False
    for target in targets:
        if not _validate_one(target=target):
            failed_any = True
    if failed_any:
        raise SystemExit(1)


def _validate_one(target: CheckTarget) -> bool:
    """Run every check on one scenario, print the outcome, and return whether it passed."""
    notes = list(target.notes)
    outcomes: list[CheckOutcome] = []
    if target.loaded is not None:
        package = check_scenario_package(loaded=target.loaded)
        notes.extend(package.notes)
        outcomes.extend(package.outcomes)
    outcomes.extend(check_scenario(scenario_cls=target.scenario_cls))

    failed = failures(outcomes)
    for outcome in failed:
        where = target.label
        if outcome.preset:
            where = f"{where} [{outcome.preset}]"
        print(f"FAIL {where}: {outcome.check} — {outcome.detail}")
    for note in notes:
        print(f"NOTE {target.label}: {note}")
    if failed:
        print(f"{len(failed)} of {len(outcomes)} checks failed for {target.label}.")
        return False
    presets = target.scenario_cls.knobs_preset_names()
    print(
        f"{target.label}: {len(outcomes)} checks passed "
        f"across {len(presets)} preset(s): {', '.join(presets)}"
    )
    return True


def handle_new_scenario(args: argparse.Namespace) -> None:
    """Write a new scenario folder and print what to do with it."""
    try:
        written = write_scenario_folder(
            scenario_name=args.scenario_name, target_dir=Path(args.target_dir)
        )
    except ScaffoldError as refusal:
        raise SystemExit(str(refusal)) from refusal

    working_dir = Path.cwd()
    folder = _shown_path(path=written.scenario_dir, working_dir=working_dir)
    print(f"Wrote {len(written.files)} files to {folder}")

    loaded_sources = current_scenario_catalog().sources
    reach = sources_reach(module_path=written.module_path, sources=loaded_sources)
    if not reach.reached:
        print()
        print(f"The scenario sources configured here do not load {folder}.")
        if reach.failure is not None:
            # The loader's error names the fix: adding the folder elsewhere would
            # fail the same way.
            print(f"  {reach.failure}")
        else:
            configured = configured_sources(sources=loaded_sources)
            if not configured:
                print("  They are none: only the built-in scenarios are loaded.")
            for source in configured:
                print(f"  {source.describe()}")
            for line in _source_fix_lines(
                cli_sources=args.scenarios,
                scenario_dir=written.scenario_dir,
                working_dir=working_dir,
                test_path=written.test_path,
            ):
                print(line)

    project = find_project(working_dir=working_dir)
    print()
    for line in next_step_lines(
        scenario_name=args.scenario_name,
        scenario_folder=folder,
        test_file=_shown_path(path=written.test_path, working_dir=working_dir),
        working_dir=working_dir,
        project=project,
        uses_uv=is_uv_project(project=project),
        environment_prefix=Path(sys.prefix),
        has_pytest=importlib.util.find_spec("pytest") is not None,
        glossogen_version=metadata.version("glossogen"),
    ):
        print(line)


def is_uv_project(project: ProjectLocation) -> bool:
    """Return whether the project is managed by uv: a ``uv.lock``, or a ``[tool.uv]`` table."""
    if (project.root / "uv.lock").is_file():
        return True
    if project.pyproject is None:
        return False
    try:
        pyproject = tomllib.loads(project.pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        logger.exception("Could not parse %s", project.pyproject)
        return False
    return "uv" in pyproject.get("tool", {})


def next_step_lines(
    scenario_name: str,
    scenario_folder: str,
    test_file: str,
    working_dir: Path,
    project: ProjectLocation,
    uses_uv: bool,
    environment_prefix: Path,
    has_pytest: bool,
    glossogen_version: str,
) -> list[str]:
    """Return the printed next steps after ``new-scenario`` wrote a folder.

    The install step is shown only when it applies: glossogen ran from an
    environment outside the project (``environment_prefix`` is not under the
    project root), or that environment lacks pytest, which the ``testing`` extra
    brings. In a uv project the commands are spelled ``uv add`` and ``uv run``.
    """
    command_prefix = ""
    if uses_uv:
        command_prefix = "uv run "
    requirement = f'"glossogen[testing] @ {GLOSSOGEN_REPOSITORY}@<tag>"'
    install_command = f"pip install {requirement}"
    if uses_uv:
        install_command = f"uv add {requirement}"
    steps: list[list[str]] = []
    outside_project = not environment_prefix.resolve().is_relative_to(project.root)
    if outside_project:
        steps.append(
            [
                f"This glossogen runs from {environment_prefix}, outside the project. "
                "Install it, with its test extra, in the project's environment:",
                f"     {install_command}",
                f"   <tag> is a release tag; this glossogen is {glossogen_version}.",
            ]
        )
    elif not has_pytest:
        steps.append(
            [
                "Add glossogen's test extra, which brings pytest:",
                f"     {install_command}",
                f"   <tag> is a release tag; this glossogen is {glossogen_version}.",
            ]
        )
    steps.append(
        [
            f"Put your provider key in {project.root / '.env'}:",
            "     ANTHROPIC_API_KEY=...",
        ]
    )
    steps.append([f"{command_prefix}glossogen validate {scenario_folder}"])
    steps.append(
        [
            f"{command_prefix}glossogen run {scenario_name} --config knobs_default "
            f"--model {SMOKE_RUN_MODEL} --provider anthropic --runs-dir ./runs round_count=1"
        ]
    )
    steps.append([f"{command_prefix}pytest {test_file}"])
    lines = [f"Next, from {working_dir}:"]
    for number, step in enumerate(steps, start=1):
        lines.append(f"  {number}. {step[0]}")
        lines.extend(f"  {continuation}" for continuation in step[1:])
    return lines


def _source_fix_lines(
    cli_sources: list[str], scenario_dir: Path, working_dir: Path, test_path: Path
) -> list[str]:
    """Say how to make every printed command, pytest included, load ``scenario_dir``.

    The fix goes where the sources came from: ``--scenarios``, then
    ``GLOSSOGEN_SCENARIOS``, then ``[tool.glossogen] scenarios``, whose paths are
    relative to the ``pyproject.toml``. pytest takes no ``--scenarios``, so with
    that source it is given ``GLOSSOGEN_SCENARIOS`` instead.
    """
    absolute = scenario_dir.resolve()
    folder = _shown_path(path=scenario_dir, working_dir=working_dir)
    test = _shown_path(path=test_path, working_dir=working_dir)
    if cli_sources:
        return [
            f"Pass --scenarios {folder} to each glossogen command below as well. pytest "
            "takes no --scenarios, so give it the folder through the environment:",
            f"    {SCENARIOS_ENV_VAR}={shlex.quote(str(absolute))} pytest {test}",
        ]
    existing = os.environ.get(SCENARIOS_ENV_VAR)
    if existing is not None:
        entries = [entry for entry in existing.split(os.pathsep) if entry.strip()]
        value = os.pathsep.join([*entries, str(absolute)])
        return [
            f"{SCENARIOS_ENV_VAR} is set, so it decides the sources and [tool.glossogen] "
            "is not read. Add the folder to it before the commands below, pytest included:",
            f"    export {SCENARIOS_ENV_VAR}={shlex.quote(value)}",
        ]
    project = find_project(working_dir=working_dir)
    pyproject = project.pyproject
    if pyproject is None:
        pyproject = project.root / "pyproject.toml"
    entry = str(absolute)
    if absolute.is_relative_to(project.root):
        entry = absolute.relative_to(project.root).as_posix()
    return [
        f"Add {json.dumps(entry)} to [tool.glossogen] scenarios in {pyproject}, creating the table "
        "if it is not there; the paths in it are relative to that file. Every command "
        "below reads it, pytest included. The list replaces the scan of the project "
        "directory, so it has to name every folder glossogen should load.",
    ]


def _shown_path(path: Path, working_dir: Path) -> str:
    """Return ``path`` as ``./<relative>`` when it is under the working directory.

    The ``./`` keeps ``validate`` from reading a folder named after its scenario
    as the scenario's name.
    """
    resolved = path.resolve()
    if resolved.is_relative_to(working_dir.resolve()):
        return f"./{resolved.relative_to(working_dir.resolve()).as_posix()}"
    return str(resolved)
