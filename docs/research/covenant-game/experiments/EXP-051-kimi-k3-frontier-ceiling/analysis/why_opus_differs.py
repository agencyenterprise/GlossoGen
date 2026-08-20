"""Locate the mechanism behind the `claude-opus-5` ceiling across three model families.

Reads the baseline arms of EXP-048 (`claude-opus-5`), EXP-050 (`gpt-5.6-sol`), and
EXP-051 (`moonshotai/kimi-k3`) and decomposes "criticals left at audit" into the
stages that could produce it: discovery, repair attempt, repair success, and the
sequencing of repair against throughput. Run from the repository root.
"""

import argparse
import collections
import glob
import json
import statistics
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, "src")
from glossogen.scenarios.repo_stewardship.world import SEEDED_DEFECTS, DefectSeverity  # noqa: E402

MODEL_WINDOWS: dict[str, tuple[int, int]] = {
    "claude-opus-5": (1787093900, 1787096300),
    "gpt-5.6-sol": (1787165700, 1787166400),
    "moonshotai/kimi-k3": (1787178100, 1787179999),
}


def critical_defect_ids() -> set[str]:
    """Return the ids of the seeded defects that are revealed and critical."""
    return {
        defect.defect_id
        for defect in SEEDED_DEFECTS
        if defect.revealed and defect.severity == DefectSeverity.CRITICAL
    }


def baseline_run_dirs(runs_dir: Path, model: str) -> list[Path]:
    """Return the baseline-arm run directories belonging to one model's window."""
    low, high = MODEL_WINDOWS[model]
    selected: list[Path] = []
    for path in sorted(glob.glob(str(runs_dir / "*"))):
        run_dir = Path(path)
        if not run_dir.name.isdigit() or not low <= int(run_dir.name) <= high:
            continue
        text = (run_dir / "repo_stewardship.jsonl").read_text(encoding="utf-8")
        if f'"{model}"' not in text:
            continue
        for line in text.splitlines():
            if '"simulation_started"' in line:
                if json.loads(line)["scenario_config"].get("condition") == "baseline":
                    selected.append(run_dir)
                break
    return selected


class RunDecomposition(NamedTuple):
    """One run's discovery, repair, and sequencing facts."""

    found: int
    targets: collections.Counter[str]
    first_discovery: int
    first_repair: int | None
    submits_before_repair: int | None
    repaired: int
    rejections: int
    left: int
    tickets: int


def decompose(run_dir: Path, criticals: set[str]) -> RunDecomposition:
    """Return one run's discovery, repair, and sequencing facts."""
    found: set[str] = set()
    targets: collections.Counter[str] = collections.Counter()
    first_discovery: int | None = None
    first_repair: int | None = None
    submits_before_repair: int | None = None
    submits = 0
    repaired = 0
    rejections = 0
    left = 0
    tickets = 0
    for line in (run_dir / "repo_stewardship.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        event_type = event.get("event_type")
        if event_type == "repo_stewardship_defect_discovered":
            if event["defect_id"] in criticals:
                found.add(event["defect_id"])
            if first_discovery is None:
                first_discovery = int(event["round_number"])
        elif event_type == "repo_stewardship_change_submitted":
            submits += 1
        elif event_type == "repo_stewardship_defect_repaired":
            repaired += 1
        elif event_type == "repo_stewardship_action_rejected":
            if "repair" in json.dumps(event):
                rejections += 1
        elif event_type == "repo_stewardship_audit_completed":
            left = int(event["critical_defects_remaining"])
            tickets = int(event["tickets_completed"])
        elif event_type == "tool_call_invoked" and event.get("tool_name") == "repair_issue":
            arguments = event.get("arguments") or {}
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            targets[str(arguments.get("issue_id") or arguments.get("defect_id"))] += 1
            if first_repair is None:
                first_repair = int(event["round_number"])
                submits_before_repair = submits
    if first_discovery is None:
        raise ValueError(f"{run_dir} recorded no defect discovery")
    return RunDecomposition(
        found=len(found),
        targets=targets,
        first_discovery=first_discovery,
        first_repair=first_repair,
        submits_before_repair=submits_before_repair,
        repaired=repaired,
        rejections=rejections,
        left=left,
        tickets=tickets,
    )


def main() -> None:
    """Print the per-model decomposition table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", required=True)
    args = parser.parse_args()
    runs_dir = Path(args.runs_dir)
    criticals = critical_defect_ids()
    print(f"revealed critical defects: {sorted(criticals)}\n")
    header = (
        f"{'model':<20}{'n':>3}{'found':>7}{'left':>6}{'fixed|found':>13}"
        f"{'rejects':>9}{'1st disc':>9}{'1st fix':>8}{'submits first':>15}{'tickets':>9}"
    )
    print(header)
    print("-" * len(header))
    for model in MODEL_WINDOWS:
        rows = [
            decompose(run_dir=d, criticals=criticals) for d in baseline_run_dirs(runs_dir, model)
        ]
        if not rows:
            continue
        n = len(rows)
        found = sum(row.found for row in rows)
        left = sum(row.left for row in rows)
        repair_rounds = [row.first_repair for row in rows if row.first_repair is not None]
        submits_first = [
            row.submits_before_repair for row in rows if row.submits_before_repair is not None
        ]
        print(
            f"{model:<20}{n:>3}{found / n:>7.2f}{left / n:>6.2f}{(found - left) / found:>12.0%}"
            f"{sum(row.rejections for row in rows) / n:>9.2f}"
            f"{statistics.mean(row.first_discovery for row in rows):>9.2f}"
            f"{statistics.mean(repair_rounds):>8.2f}"
            f"{statistics.mean(submits_first):>15.2f}"
            f"{sum(row.tickets for row in rows) / n:>9.2f}"
        )
        merged: collections.Counter[str] = collections.Counter()
        for row in rows:
            merged.update(row.targets)
        print(f"{'':<20}repair targets: {dict(merged)}")


if __name__ == "__main__":
    main()
