r"""Audit recorded spot_the_intersection runs on the boards their viewers were sent.

Takes one or more run directories, prints one line per run and every problem
found beneath it, and exits non-zero if any run has one. Rounds whose recorded
boards differ from what this checkout would generate, or that this checkout
cannot generate, are listed as notes: they do not fail the audit, but runs with
and without them did not play the same boards. Run it on the first runs of a
cohort, before launching the rest:

    VIRTUAL_ENV= uv run --no-sync python -m \
      glossogen.scenarios.spot_the_intersection.scripts.audit_recorded_boards \
      runs/spot_the_intersection/<run_id> [...]
"""

import argparse
import asyncio
import sys
from pathlib import Path

from glossogen.run_storage.event_log_reader import load_events
from glossogen.run_storage.run_file_paths import event_log_path
from glossogen.scenario_contract.scenario_sources import (
    load_configured_scenario_catalog_unless_loaded,
)
from glossogen.scenarios.spot_the_intersection.recorded_board_audit import audit_events
from glossogen.scenarios.spot_the_intersection.scenario import SpotTheIntersectionScenario


async def audit_run_dir(run_dir: Path) -> bool:
    """Audit one run directory and print what was found; return whether it passed."""
    log_path = event_log_path(run_dir=run_dir, scenario_name=SpotTheIntersectionScenario.name())
    audit = audit_events(events=await load_events(log_path=log_path))
    status = "OK"
    if audit.findings:
        status = "FAILED"
    print(f"{status} {run_dir}: {audit.rounds_audited} round(s), {len(audit.findings)} problem(s)")
    for finding in audit.findings:
        print(f"    round {finding.round_number}: {finding.problem}")
    if audit.regenerated_differently:
        rounds = ", ".join(str(number) for number in audit.regenerated_differently)
        print(f"    NOTE: rounds {rounds} differ from what this checkout generates")
    for note in audit.not_regenerated:
        print(f"    NOTE: round {note.round_number} cannot be generated here: {note.problem}")
    return not audit.findings


async def audit_all(run_dirs: list[Path]) -> bool:
    """Audit every run directory; return whether all passed."""
    passed = [await audit_run_dir(run_dir=run_dir) for run_dir in run_dirs]
    return all(passed)


def main() -> None:
    """Audit the run directories named on the command line; exit 1 on any problem."""
    parser = argparse.ArgumentParser(
        description="Audit recorded spot_the_intersection runs on the boards viewers were sent."
    )
    parser.add_argument("run_dirs", nargs="+", type=Path)
    args = parser.parse_args()
    load_configured_scenario_catalog_unless_loaded()
    if not asyncio.run(audit_all(run_dirs=args.run_dirs)):
        sys.exit(1)


if __name__ == "__main__":
    main()
