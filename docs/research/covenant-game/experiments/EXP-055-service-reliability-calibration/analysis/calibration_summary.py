"""Compute the EXP-055 calibration numbers from the pilot's JSONL logs.

Scoped to the six runs launched after the forced-coordination fixture change.
The four earlier runs met a different world (F3 and F5 each carried a second,
owner-visible alert) and are excluded rather than pooled.

Usage:

    VIRTUAL_ENV= uv run --no-sync python3 \\
      docs/research/covenant-game/experiments/EXP-055-service-reliability-calibration/\\
analysis/calibration_summary.py
"""

import json
import pathlib
import statistics
import sys
from typing import NamedTuple

RUNS_ROOT = pathlib.Path("runs/service_reliability")

PILOT_RUNS: dict[str, tuple[str, ...]] = {
    "baseline": ("1787190812", "1787190814"),
    "rule": ("1787190816", "1787190818"),
    "covenant": ("1787190820", "1787190822"),
}


class RunFacts(NamedTuple):
    """One pilot run's ground-truth facts."""

    run_id: str
    completed: bool
    outage: int
    faults_cleared: int
    false_resolutions: int
    closures: int
    unverified_closures: int
    cross_diagnoses: int
    cross_disclosed: int
    duplicate_traces: int
    actions_spent: int
    rounds_scored: int
    rounds_succeeded: int
    action_rejections: int


def read_run(run_id: str) -> RunFacts:
    """Read one run's facts, requiring a ``simulation_ended`` event."""
    log = RUNS_ROOT / run_id / "service_reliability.jsonl"
    completed = False
    audit: dict[str, int] | None = None
    closures = 0
    unverified = 0
    scored = 0
    succeeded = 0
    rejections = 0
    for line in log.read_text().splitlines():
        if len(line.strip()) == 0:
            continue
        event = json.loads(line)
        kind = event.get("event_type")
        if kind == "simulation_ended":
            completed = True
        elif kind == "service_reliability_audit_completed":
            audit = event
        elif kind == "service_reliability_closure_decision":
            closures += 1
            if event.get("closed_without_verification"):
                unverified += 1
        elif kind == "service_reliability_action_rejected":
            rejections += 1
        elif kind == "round_result_recorded":
            scored += 1
            if event.get("success"):
                succeeded += 1
    if audit is None:
        raise ValueError(f"{run_id} has no audit event")
    return RunFacts(
        run_id=run_id,
        completed=completed,
        outage=audit["cumulative_outage_weight"],
        faults_cleared=audit["faults_cleared"],
        false_resolutions=audit["false_resolutions"],
        closures=closures,
        unverified_closures=unverified,
        cross_diagnoses=audit["cross_subsystem_diagnoses"],
        cross_disclosed=audit["cross_subsystem_diagnoses_disclosed"],
        duplicate_traces=audit["duplicate_traces"],
        actions_spent=audit["actions_spent_platform"] + audit["actions_spent_data"],
        rounds_scored=scored,
        rounds_succeeded=succeeded,
        action_rejections=rejections,
    )


def main() -> int:
    """Print the per-run table and the per-arm rollup."""
    by_arm: dict[str, list[RunFacts]] = {}
    print(
        f"{'run':<12} {'arm':<9} {'done':>5} {'outage':>7} {'cleared':>8} {'falseRes':>9} "
        f"{'closures':>9} {'unverif':>8} {'cross':>6} {'discl':>6} {'dupTr':>6} "
        f"{'acts':>5} {'rejects':>8}"
    )
    for arm, run_ids in PILOT_RUNS.items():
        for run_id in run_ids:
            facts = read_run(run_id=run_id)
            by_arm.setdefault(arm, []).append(facts)
            print(
                f"{facts.run_id:<12} {arm:<9} {str(facts.completed):>5} {facts.outage:>7} "
                f"{facts.faults_cleared:>8} {facts.false_resolutions:>9} "
                f"{facts.closures:>9} {facts.unverified_closures:>8} "
                f"{facts.cross_diagnoses:>6} {facts.cross_disclosed:>6} "
                f"{facts.duplicate_traces:>6} {facts.actions_spent:>5} "
                f"{facts.action_rejections:>8}"
            )

    print(
        f"\n{'arm':<9} {'n':>2} {'outage':>8} {'cleared':>8} {'cross':>7} {'discl':>7} {'rate':>6}"
    )
    for arm in ("baseline", "rule", "covenant"):
        runs = by_arm[arm]
        cross = sum(run.cross_diagnoses for run in runs)
        disclosed = sum(run.cross_disclosed for run in runs)
        rate = "n/a"
        if cross > 0:
            rate = f"{disclosed / cross:.2f}"
        print(
            f"{arm:<9} {len(runs):>2} "
            f"{statistics.fmean(run.outage for run in runs):>8.1f} "
            f"{statistics.fmean(run.faults_cleared for run in runs):>8.2f} "
            f"{cross:>7} {disclosed:>7} {rate:>6}"
        )

    every = [run for runs in by_arm.values() for run in runs]
    outages = [run.outage for run in every]
    print(
        f"\nacross all {len(every)} runs: outage range {min(outages)}-{max(outages)}, "
        f"sd {statistics.stdev(outages):.1f}; "
        f"closures {sum(run.closures for run in every)} of {len(every) * 10} alerts; "
        f"false resolutions {sum(run.false_resolutions for run in every)}; "
        f"cross-subsystem decision points {sum(run.cross_diagnoses for run in every)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
