"""The ``validate`` and ``new-scenario`` subcommands."""

import argparse
from pathlib import Path

from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.scenario_authoring.scenario_conformance import CheckOutcome, check_scenario, failures
from glossogen.scenario_authoring.scenario_package_checks import check_scenario_package
from glossogen.scenario_authoring.scenario_scaffold import (
    SCENARIOS_FOLDER,
    ScaffoldError,
    default_glossogen_ref,
    write_scenario_package,
)
from glossogen.scenario_authoring.scenario_target import (
    CheckTarget,
    ScenarioPathError,
    resolve_check_targets,
)


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
        help="Write a runnable scenario project of your own",
    )
    new_scenario_parser.add_argument(
        "scenario_name",
        type=str,
        help=(
            "Name of the scenario to create. Becomes the module, the name given to "
            "@scenario and the run directory, so it has to be a lowercase identifier"
        ),
    )
    new_scenario_parser.add_argument(
        "--target-dir",
        type=str,
        required=True,
        help="Directory to write the new project into",
    )
    new_scenario_parser.add_argument(
        "--glossogen-ref",
        type=str,
        default=None,
        help=(
            "Git ref the generated pyproject.toml pins glossogen to. Defaults to "
            "the release tag matching the installed version"
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
    """Write a new scenario project and print what to do with it."""
    ref = args.glossogen_ref
    if ref is None:
        ref = default_glossogen_ref()

    try:
        package = write_scenario_package(
            scenario_name=args.scenario_name,
            target_dir=Path(args.target_dir),
            glossogen_ref=ref,
        )
    except ScaffoldError as refusal:
        raise SystemExit(str(refusal)) from refusal

    print(f"Wrote {len(package.files)} files to {package.package_dir}")
    # Named because it is inferred from the installed version unless it was
    # passed, and it is what the generated project installs glossogen from.
    print(f"Pinned to glossogen {ref}; pass --glossogen-ref to pin another.")
    print(f"  cd {package.package_dir}")
    print(
        f"  glossogen validate {SCENARIOS_FOLDER}/{args.scenario_name}.py"
        "   # the contract, no API key"
    )
    print('  pip install -e ".[testing]"')
    print("  pytest")
