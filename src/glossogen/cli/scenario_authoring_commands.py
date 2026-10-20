"""The ``validate`` and ``new-scenario`` subcommands."""

import argparse
from pathlib import Path

from glossogen.cli.subcommand_parsers import SubcommandParsers
from glossogen.scenario_authoring.scenario_conformance import CheckOutcome, check_scenario, failures
from glossogen.scenario_authoring.scenario_package_checks import check_scenario_package
from glossogen.scenario_authoring.scenario_scaffold import (
    ScaffoldError,
    default_glossogen_ref,
    write_scenario_package,
)
from glossogen.scenario_authoring.scenario_target import ScenarioPathError, resolve_check_target
from glossogen.scenario_path_loader import registered_for_checks


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
            "An installed scenario's name, or the directory holding a package's "
            "pyproject.toml, which is the one `new-scenario` created rather than the "
            f"module inside it. Installed: {', '.join(scenario_names)}"
        ),
    )


def add_new_scenario_parser(subparsers: SubcommandParsers) -> None:
    """Add the ``new-scenario`` subcommand and its flags."""
    new_scenario_parser = subparsers.add_parser(
        "new-scenario",
        help="Write a runnable scenario package of your own",
    )
    new_scenario_parser.add_argument(
        "scenario_name",
        type=str,
        help=(
            "Name of the scenario to create. Becomes the package directory, the "
            "module, the entry-point key and what name() returns, so it has to be "
            "a lowercase identifier"
        ),
    )
    new_scenario_parser.add_argument(
        "--target-dir",
        type=str,
        required=True,
        help="Directory to write the new package into",
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
    """Check a scenario against the contract and report everything that failed.

    Takes a name or a directory. Which one it was decides only how the class is
    found: the contract checks are the same either way. A directory additionally
    gets the package checks, which are about the distribution around the scenario
    and so have nothing to look at once that distribution is installed.

    Exits non-zero when anything failed, so this works as a CI step in whichever
    package ships the scenario.

    Needs no API key, and checks no model's reachability: describing a scenario
    must not require a credential, and a launch checks what it can reach where the
    run's own model and provider are known.
    """
    try:
        target = resolve_check_target(target=args.target)
    except (ScenarioPathError, ValueError) as refusal:
        raise SystemExit(f"FAIL {args.target}: {refusal}") from refusal

    notes = list(target.notes)
    outcomes: list[CheckOutcome] = []
    if target.loaded is None:
        outcomes.extend(check_scenario(scenario_cls=target.scenario_cls))
    else:
        # The package checks run first and outside the registration below, because
        # the collision check has to see the registry as it really is.
        package = check_scenario_package(loaded=target.loaded)
        notes.extend(package.notes)
        with registered_for_checks(loaded=target.loaded):
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
        # Printed rather than raised with a message, so the summary lands after
        # the failures it counts rather than ahead of them on another stream.
        print(f"{len(failed)} of {len(outcomes)} checks failed for {target.label}.")
        raise SystemExit(1)
    presets = target.scenario_cls.knobs_preset_names()
    print(
        f"{target.label}: {len(outcomes)} checks passed "
        f"across {len(presets)} preset(s): {', '.join(presets)}"
    )


def handle_new_scenario(args: argparse.Namespace) -> None:
    """Write a new scenario package and print what to do with it.

    The next steps are printed rather than left to the README, because their order
    is not obvious: `validate` reads the package's own declaration and so works on
    what was just written, while `pytest` needs the install for the harness.
    """
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
    # passed, and it is what the generated package installs glossogen from.
    print(f"Pinned to glossogen {ref}; pass --glossogen-ref to pin another.")
    print(f"  cd {package.package_dir}")
    print("  glossogen validate .            # the contract, before installing anything")
    print('  pip install -e ".[testing]"')
    print("  pytest")
