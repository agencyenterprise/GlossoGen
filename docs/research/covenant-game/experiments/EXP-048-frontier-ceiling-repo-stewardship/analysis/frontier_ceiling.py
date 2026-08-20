"""Derive EXP-048's reported numbers from the repo-stewardship event logs.

Reduces every completed run to one outcome row per simulation, groups the rows by
(model, arm), and prints the per-arm means plus the within-arm range for each
outcome. The range is the point of this experiment: an arm whose ten runs share
one value on an outcome has no variance for a treatment to act on, and that is
reported explicitly rather than inferred from a mean.

Run from the repository root:

    VIRTUAL_ENV= uv run --no-sync python \
        docs/research/covenant-game/experiments/\
EXP-048-frontier-ceiling-repo-stewardship/analysis/frontier_ceiling.py \
        --runs-dir runs/repo_stewardship --model claude-opus-5
"""

import argparse
import json
from pathlib import Path
from typing import NamedTuple

from glossogen.scenarios.repo_stewardship.scripts.summarize_runs import RunSummary, summarize_run

REPORTED_OUTCOMES = (
    "developer_releases",
    "reviewer_releases",
    "joint_breaches",
    "repairs",
    "disclosures",
    "correct_approvals",
    "false_approvals",
    "correct_blocks",
    "false_blocks",
    "unreviewed_tickets",
    "tickets_completed",
    "critical_defects_remaining",
    "final_integrity_score",
    "rejected_actions",
)


class ArmStatistic(NamedTuple):
    """One outcome's mean and observed range within one arm."""

    outcome: str
    mean: float
    minimum: float
    maximum: float
    is_constant: bool


def registered_model(run_dir: Path) -> str | None:
    """Return the model named by the run's first agent_registered event."""
    log_path = run_dir / "repo_stewardship.jsonl"
    if not log_path.exists():
        return None
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            if '"agent_registered"' not in line:
                continue
            return json.loads(line).get("model")
    return None


def collect_rows(runs_dir: Path, model: str) -> dict[str, list[RunSummary]]:
    """Return completed run summaries for one model, grouped by arm label."""
    grouped: dict[str, list[RunSummary]] = {}
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        summary = summarize_run(run_dir=run_dir)
        if summary is None or not summary.completed:
            continue
        if registered_model(run_dir=run_dir) != model:
            continue
        grouped.setdefault(summary.condition, []).append(summary)
    return grouped


def arm_statistics(rows: list[RunSummary]) -> list[ArmStatistic]:
    """Return the mean and range of every reported outcome for one arm."""
    statistics: list[ArmStatistic] = []
    for outcome in REPORTED_OUTCOMES:
        values = [float(getattr(row, outcome)) for row in rows]
        statistics.append(
            ArmStatistic(
                outcome=outcome,
                mean=sum(values) / len(values),
                minimum=min(values),
                maximum=max(values),
                is_constant=min(values) == max(values),
            )
        )
    return statistics


def main() -> None:
    """Print per-arm means and ranges for one model's completed runs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--model", type=str, required=True)
    args = parser.parse_args()
    grouped = collect_rows(runs_dir=args.runs_dir, model=args.model)
    arms = sorted(grouped)
    print(f"model: {args.model}")
    for arm in arms:
        rows = grouped[arm]
        print(f"\n{arm} (n={len(rows)})")
        print(f"  {'outcome':<28}{'mean':>8}{'min':>7}{'max':>7}  constant")
        for statistic in arm_statistics(rows=rows):
            flag = ""
            if statistic.is_constant:
                flag = "  <- no variance"
            print(
                f"  {statistic.outcome:<28}{statistic.mean:>8.2f}"
                f"{statistic.minimum:>7.2f}{statistic.maximum:>7.2f}{flag}"
            )


if __name__ == "__main__":
    main()
