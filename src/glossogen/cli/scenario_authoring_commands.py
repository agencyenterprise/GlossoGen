"""The ``validate`` and ``new-scenario`` subcommands."""

import argparse
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
from glossogen.scenario_contract.scenario_sources import find_project

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
    if not sources_reach(module_path=written.module_path, sources=loaded_sources):
        configured = configured_sources(sources=loaded_sources)
        listed = "    none: only the built-in scenarios are loaded"
        if configured:
            listed = "\n".join(f"    {source.describe()}" for source in configured)
        print()
        print(f"The scenario sources configured here do not reach {folder}:")
        print(listed)
        print(
            f'Add "{folder}" to [tool.glossogen] scenarios in your pyproject.toml, or '
            f"pass --scenarios {folder} before each subcommand below."
        )

    project_root = find_project(working_dir=working_dir).root
    print()
    print(f"Next, from {working_dir}:")
    print("  1. Install glossogen, with its test extra, in this project's environment:")
    print(f'       pip install "glossogen[testing] @ {GLOSSOGEN_REPOSITORY}@<tag>"')
    print(f"     <tag> is a release tag; this glossogen is {metadata.version('glossogen')}.")
    print(f"  2. Put your provider key in {project_root / '.env'}:")
    print("       ANTHROPIC_API_KEY=...")
    print(f"  3. glossogen validate {folder}")
    print(
        f"  4. glossogen run {args.scenario_name} --config knobs_default "
        f"--model {SMOKE_RUN_MODEL} --provider anthropic --runs-dir ./runs round_count=1"
    )
    print(f"  5. pytest {_shown_path(path=written.test_path, working_dir=working_dir)}")


def _shown_path(path: Path, working_dir: Path) -> str:
    """Return ``path`` as ``./<relative>`` when it is under the working directory.

    The ``./`` keeps ``validate`` from reading a folder named after its scenario
    as the scenario's name.
    """
    resolved = path.resolve()
    if resolved.is_relative_to(working_dir.resolve()):
        return f"./{resolved.relative_to(working_dir.resolve()).as_posix()}"
    return str(resolved)
