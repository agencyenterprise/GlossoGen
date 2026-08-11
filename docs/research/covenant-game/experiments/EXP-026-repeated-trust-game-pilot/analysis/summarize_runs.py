"""Derive repeated trust-game outcomes from authoritative JSONL events."""

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def load_events(path: Path) -> list[dict[str, Any]]:
    """Load JSONL events from one simulation log."""
    with path.open(encoding="utf-8") as event_file:
        return [json.loads(line) for line in event_file if line.strip()]


def require_event(events: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    """Return the single event type expected to occur once in a run."""
    matches = [event for event in events if event["event_type"] == event_type]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {event_type}, found {len(matches)}")
    return matches[0]


def mean(values: list[float]) -> float:
    """Return a mean while rejecting empty metric series."""
    if not values:
        raise ValueError("Cannot calculate a mean of no values")
    return statistics.fmean(values)


def sample_standard_deviation(values: list[float]) -> float:
    """Return sample spread, or zero for a single trajectory."""
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values)


def summarize_run(run_dir: Path) -> dict[str, Any]:
    """Summarize role-specific choices, treatment exposure, and run completion."""
    event_path = run_dir / "repeated_trust_game.jsonl"
    events = load_events(path=event_path)
    started = require_event(events=events, event_type="simulation_started")
    ended = require_event(events=events, event_type="simulation_ended")
    config = started["scenario_config"]
    if not isinstance(config, dict):
        raise ValueError(f"Missing scenario configuration in {run_dir}")
    condition = config["condition"]
    if not isinstance(condition, str):
        raise ValueError(f"Missing condition in {run_dir}")

    decisions = [
        event for event in events if event["event_type"] == "repeated_trust_decision_recorded"
    ]
    trust_sent = [float(event["amount"]) for event in decisions if event["role"] == "trustor"]
    reciprocity_returned = [
        float(event["amount"]) for event in decisions if event["role"] == "trustee"
    ]
    pledges = [
        event for event in events if event["event_type"] == "repeated_trust_pledge_submitted"
    ]
    forfeiture_paid = sum(float(event["forfeiture_paid"]) for event in decisions)

    return {
        "run_dir": str(run_dir),
        "condition": condition,
        "completed": ended["reason"] == "scenario_complete",
        "total_cost_usd": float(ended["total_cost_usd"]),
        "trust_decisions": len(trust_sent),
        "trust_mean_sent": mean(values=trust_sent),
        "trust_values": trust_sent,
        "reciprocity_decisions": len(reciprocity_returned),
        "reciprocity_mean_returned": mean(values=reciprocity_returned),
        "reciprocity_values": reciprocity_returned,
        "pledge_events": len(pledges),
        "pledge_decisions": [event["decision"] for event in pledges],
        "forfeiture_paid": forfeiture_paid,
    }


def summarize_condition(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate completed-run means within one experimental condition."""
    trust_means = [float(run["trust_mean_sent"]) for run in runs]
    reciprocity_means = [float(run["reciprocity_mean_returned"]) for run in runs]
    costs = [float(run["total_cost_usd"]) for run in runs]
    return {
        "runs": len(runs),
        "mean_trust_sent": mean(values=trust_means),
        "sample_sd_trust_sent": sample_standard_deviation(values=trust_means),
        "mean_reciprocity_returned": mean(values=reciprocity_means),
        "sample_sd_reciprocity_returned": sample_standard_deviation(values=reciprocity_means),
        "total_cost_usd": sum(costs),
    }


def main() -> None:
    """Write a reproducible JSON summary for explicitly named run directories."""
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    run_summaries = [summarize_run(run_dir=run_dir) for run_dir in arguments.run_dirs]
    grouped_runs: dict[str, list[dict[str, Any]]] = {}
    for run in run_summaries:
        condition = str(run["condition"])
        grouped_runs.setdefault(condition, []).append(run)
    conditions = {
        condition: summarize_condition(runs=runs)
        for condition, runs in sorted(grouped_runs.items())
    }
    arguments.output.write_text(
        json.dumps({"runs": run_summaries, "conditions": conditions}, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
