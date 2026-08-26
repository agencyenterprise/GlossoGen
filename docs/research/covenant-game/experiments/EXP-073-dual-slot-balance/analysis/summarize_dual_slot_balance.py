"""Summarize the frozen EXP-073 dual-slot baseline screen."""

import argparse
import json
from pathlib import Path

MODELS = ("claude-sonnet-5", "claude-haiku-4-5-20251001")
CELL = "balance_paired_matched_priority"
EXPECTED_RUNS = 8
MIN_FOCAL = 2
MAX_FOCAL = 6


def _parse_args() -> argparse.Namespace:
    """Parse the canonical runs directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    return parser.parse_args()


def _endpoint(log_path: Path) -> dict[str, object]:
    """Return the single valid agent-completed endpoint from one log."""
    events = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    simulation_ends = [
        event for event in events if event.get("event_type") == "simulation_ended"
    ]
    if len(simulation_ends) != 1 or simulation_ends[0].get("reason") != "scenario_complete":
        raise ValueError(f"{log_path}: missing normal simulation end")
    endpoints = [
        event
        for event in events
        if event.get("event_type") == "benjamin_capacity_crossroads_completed"
    ]
    if len(endpoints) != 1 or endpoints[0].get("completed_by_agent") is not True:
        raise ValueError(f"{log_path}: missing agent-completed atomic endpoint")
    return endpoints[0]


def summarize(runs_root: Path) -> dict[str, object]:
    """Apply the frozen per-family baseline eligibility rule."""
    experiment_root = runs_root / "covenant-game" / "EXP-073"
    family_results: list[dict[str, object]] = []
    for model in MODELS:
        logs = sorted(
            (experiment_root / model / "balance" / CELL).glob(
                "**/benjamin_dual_slot_allocation.jsonl"
            )
        )
        if len(logs) != EXPECTED_RUNS:
            raise ValueError(f"{model}: expected {EXPECTED_RUNS} logs, found {len(logs)}")
        endpoints = [_endpoint(log_path=log_path) for log_path in logs]
        focal = sum(endpoint.get("focal_fixed") is True for endpoint in endpoints)
        transfer = sum(endpoint.get("transfer_fixed") is True for endpoint in endpoints)
        family_results.append(
            {
                "model": model,
                "valid_runs": len(endpoints),
                "focal_fixed": focal,
                "transfer_fixed": transfer,
                "eligible": MIN_FOCAL <= focal <= MAX_FOCAL,
            }
        )
    return {
        "expected_runs_per_family": EXPECTED_RUNS,
        "eligible_focal_count_interval": [MIN_FOCAL, MAX_FOCAL],
        "families": family_results,
        "instrument_eligible": all(result["eligible"] for result in family_results),
    }


def main() -> int:
    """Print the frozen dual-slot summary as JSON."""
    summary = summarize(runs_root=_parse_args().runs_root.resolve())
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
