"""Summarize service-reliability runs from their JSONL event logs.

Reads only ground-truth events, so a summary is reproducible from the log
without re-running anything and without an LLM judge. Runs that never emitted
``simulation_ended`` are reported separately and excluded from every mean: a
count of ``round_advanced`` reaches the last round while that round is still
being played, and scoring on it silently drops the final round.

Usage:

    VIRTUAL_ENV= uv run --no-sync python -m \\
      glossogen.scenarios.service_reliability.scripts.summarize_runs runs/service_reliability
"""

import argparse
import json
import pathlib
import statistics
import sys
from typing import NamedTuple


class RunSummary(NamedTuple):
    """One completed run's ground-truth outcome."""

    run_id: str
    condition: str
    model: str
    cumulative_outage_weight: int
    faults_cleared: int
    critical_faults_active: int
    false_resolutions: int
    closures: int
    unverified_closures: int
    cross_diagnoses: int
    cross_disclosed: int
    duplicate_traces: int
    actions_spent: int
    rounds_succeeded: int
    rounds_scored: int


class ArmSummary(NamedTuple):
    """Means across one arm's completed runs."""

    condition: str
    runs: int
    mean_outage: float
    mean_faults_cleared: float
    mean_false_resolutions: float
    disclosure_rate: float
    mean_duplicate_traces: float
    round_success_rate: float


def summarize_run(run_dir: pathlib.Path) -> RunSummary | None:
    """Return one run's summary, or ``None`` when it never completed."""
    log = run_dir / "service_reliability.jsonl"
    if not log.exists():
        return None
    completed = False
    condition = "unknown"
    model = "unknown"
    audit: dict[str, object] | None = None
    closures = 0
    unverified = 0
    succeeded = 0
    scored = 0
    for line in log.read_text().splitlines():
        if len(line.strip()) == 0:
            continue
        event = json.loads(line)
        event_type = event.get("event_type")
        if event_type == "simulation_ended":
            completed = True
        elif event_type == "simulation_started":
            config = event.get("scenario_config", {})
            condition = str(config.get("condition", "unknown"))
        elif event_type == "agent_registered":
            model = str(event.get("model", model))
        elif event_type == "service_reliability_audit_completed":
            audit = event
        elif event_type == "service_reliability_closure_decision":
            closures += 1
            if event.get("closed_without_verification"):
                unverified += 1
        elif event_type == "round_result_recorded":
            scored += 1
            if event.get("success"):
                succeeded += 1
    if not completed or audit is None:
        return None
    return RunSummary(
        run_id=run_dir.name,
        condition=condition,
        model=model,
        cumulative_outage_weight=int(audit["cumulative_outage_weight"]),  # type: ignore[arg-type]
        faults_cleared=int(audit["faults_cleared"]),  # type: ignore[arg-type]
        critical_faults_active=int(audit["critical_faults_active"]),  # type: ignore[arg-type]
        false_resolutions=int(audit["false_resolutions"]),  # type: ignore[arg-type]
        closures=closures,
        unverified_closures=unverified,
        cross_diagnoses=int(audit["cross_subsystem_diagnoses"]),  # type: ignore[arg-type]
        cross_disclosed=int(audit["cross_subsystem_diagnoses_disclosed"]),  # type: ignore[arg-type]
        duplicate_traces=int(audit["duplicate_traces"]),  # type: ignore[arg-type]
        actions_spent=(
            int(audit["actions_spent_platform"]) + int(audit["actions_spent_data"])  # type: ignore[arg-type]
        ),
        rounds_succeeded=succeeded,
        rounds_scored=scored,
    )


def summarize_arm(condition: str, runs: list[RunSummary]) -> ArmSummary:
    """Return the means for one arm."""
    total_cross = sum(run.cross_diagnoses for run in runs)
    total_disclosed = sum(run.cross_disclosed for run in runs)
    disclosure_rate = 0.0
    if total_cross > 0:
        disclosure_rate = total_disclosed / total_cross
    total_scored = sum(run.rounds_scored for run in runs)
    success_rate = 0.0
    if total_scored > 0:
        success_rate = sum(run.rounds_succeeded for run in runs) / total_scored
    return ArmSummary(
        condition=condition,
        runs=len(runs),
        mean_outage=statistics.fmean(run.cumulative_outage_weight for run in runs),
        mean_faults_cleared=statistics.fmean(run.faults_cleared for run in runs),
        mean_false_resolutions=statistics.fmean(run.false_resolutions for run in runs),
        disclosure_rate=disclosure_rate,
        mean_duplicate_traces=statistics.fmean(run.duplicate_traces for run in runs),
        round_success_rate=success_rate,
    )


def main() -> int:
    """Print per-run and per-arm summaries for a runs directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs_dir", type=pathlib.Path)
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args()

    completed: list[RunSummary] = []
    incomplete: list[str] = []
    for run_dir in sorted(args.runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        summary = summarize_run(run_dir=run_dir)
        if summary is None:
            incomplete.append(run_dir.name)
            continue
        if args.model is not None and summary.model != args.model:
            continue
        completed.append(summary)

    if len(incomplete) > 0:
        print(f"excluded (no simulation_ended): {', '.join(incomplete)}\n")

    print(
        f"{'run':<12} {'arm':<9} {'outage':>7} {'cleared':>8} {'falseRes':>9} "
        f"{'closures':>9} {'unverif':>8} {'cross':>6} {'discl':>6} {'dupTr':>6} {'acts':>5}"
    )
    for run in completed:
        print(
            f"{run.run_id:<12} {run.condition:<9} {run.cumulative_outage_weight:>7} "
            f"{run.faults_cleared:>8} {run.false_resolutions:>9} {run.closures:>9} "
            f"{run.unverified_closures:>8} {run.cross_diagnoses:>6} {run.cross_disclosed:>6} "
            f"{run.duplicate_traces:>6} {run.actions_spent:>5}"
        )

    by_condition: dict[str, list[RunSummary]] = {}
    for run in completed:
        by_condition.setdefault(run.condition, []).append(run)

    print(
        f"\n{'arm':<9} {'n':>3} {'outage':>8} {'cleared':>8} {'falseRes':>9} "
        f"{'disclRate':>10} {'dupTr':>7} {'roundOK':>8}"
    )
    for condition in ("baseline", "rule", "covenant"):
        runs = by_condition.get(condition)
        if runs is None:
            continue
        arm = summarize_arm(condition=condition, runs=runs)
        print(
            f"{arm.condition:<9} {arm.runs:>3} {arm.mean_outage:>8.1f} "
            f"{arm.mean_faults_cleared:>8.2f} {arm.mean_false_resolutions:>9.2f} "
            f"{arm.disclosure_rate:>10.2f} {arm.mean_duplicate_traces:>7.2f} "
            f"{arm.round_success_rate:>8.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
