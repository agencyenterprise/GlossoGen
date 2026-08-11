"""Summarize authoritative EXP-030 event logs into a reproducible Markdown table."""

import argparse
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class RunSummary:
    """Aggregate outcome counts for one completed EXP-030 run."""

    run_id: str
    condition: str
    completed: bool
    decision_count: int
    remits: int
    retains: int
    matching_public_records: int
    settled_rounds: int
    safe_rounds: int
    pledge_affirmations: int
    pledge_declines: int
    entry_cost_events: int
    entry_cost_total: Decimal
    accepted_messages: int
    total_cost_usd: Decimal
    event_log_sha256: str
    resolved_config_sha256: str


def parse_arguments() -> argparse.Namespace:
    """Parse the run directories to summarize."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", action="append", required=True)
    return parser.parse_args()


def event_log_path(run_dir: Path) -> Path:
    """Return the JSONL event log path for one joint-commitment run."""

    return run_dir / "joint_commitment.jsonl"


def load_events(run_dir: Path) -> list[dict[str, object]]:
    """Load every JSONL event from one run archive."""

    path = event_log_path(run_dir=run_dir)
    events: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as event_file:
        for line in event_file:
            events.append(json.loads(line))
    return events


def compute_sha256(path: Path) -> str:
    """Return the SHA-256 hash for one immutable run artifact."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_run(run_dir: Path) -> RunSummary:
    """Derive EXP-030 outcomes from its authoritative scenario events."""

    events = load_events(run_dir=run_dir)
    started_event = next(event for event in events if event["event_type"] == "simulation_started")
    scenario_config = started_event["scenario_config"]
    if not isinstance(scenario_config, dict):
        raise ValueError(f"Missing scenario configuration in {run_dir}")
    condition = str(scenario_config["condition"])
    simulation_ended_events = [
        event for event in events if event["event_type"] == "simulation_ended"
    ]
    if len(simulation_ended_events) != 1:
        raise ValueError(f"Expected one simulation_ended event in {run_dir}")
    ended_event = simulation_ended_events[0]
    decisions = [
        event for event in events if event["event_type"] == "joint_commitment_decision_recorded"
    ]
    settlements = [
        event for event in events if event["event_type"] == "joint_commitment_round_settled"
    ]
    pledges = [
        event for event in events if event["event_type"] == "joint_commitment_pledge_submitted"
    ]
    entry_costs = [
        event
        for event in events
        if event["event_type"] == "joint_commitment_pledge_entry_cost_paid"
    ]
    remits = sum(1 for event in decisions if event["actual_action"] == "remit")
    retains = sum(1 for event in decisions if event["actual_action"] == "retain")
    matching_public_records = sum(
        1
        for event in decisions
        if (event["actual_action"] == "remit" and event["public_attestation"] == "remitted")
        or (event["actual_action"] == "retain" and event["public_attestation"] == "retained")
    )
    safe_rounds = sum(1 for event in settlements if event["safe_client_outcome"] is True)
    pledge_affirmations = sum(1 for event in pledges if event["decision"] == "affirm")
    pledge_declines = sum(1 for event in pledges if event["decision"] == "decline")
    entry_cost_total = sum((Decimal(str(event["amount"])) for event in entry_costs), Decimal("0"))
    accepted_messages = sum(1 for event in events if event["event_type"] == "message_sent")
    ended_cost = Decimal(str(ended_event["total_cost_usd"]))
    config_payload = json.dumps(scenario_config, sort_keys=True, separators=(",", ":")).encode()
    return RunSummary(
        run_id=str(started_event["run_id"]),
        condition=condition,
        completed=ended_event["reason"] == "scenario_complete",
        decision_count=len(decisions),
        remits=remits,
        retains=retains,
        matching_public_records=matching_public_records,
        settled_rounds=len(settlements),
        safe_rounds=safe_rounds,
        pledge_affirmations=pledge_affirmations,
        pledge_declines=pledge_declines,
        entry_cost_events=len(entry_costs),
        entry_cost_total=entry_cost_total,
        accepted_messages=accepted_messages,
        total_cost_usd=ended_cost,
        event_log_sha256=compute_sha256(path=event_log_path(run_dir=run_dir)),
        resolved_config_sha256=hashlib.sha256(config_payload).hexdigest(),
    )


def print_report(summaries: list[RunSummary]) -> None:
    """Print the per-run and pooled EXP-030 Markdown tables."""

    print(
        "| Run | Condition | Completed | Remit / retain | Matching records | "
        "Safe / settled | Pledge affirm / decline | Entry cost | Messages | API cost |"
    )
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for summary in summaries:
        print(
            f"| {summary.run_id} | {summary.condition} | {summary.completed} | "
            f"{summary.remits} / {summary.retains} | "
            f"{summary.matching_public_records}/{summary.decision_count} | "
            f"{summary.safe_rounds}/{summary.settled_rounds} | "
            f"{summary.pledge_affirmations}/{summary.pledge_declines} | "
            f"{summary.entry_cost_events} (${summary.entry_cost_total}) | "
            f"{summary.accepted_messages} | ${summary.total_cost_usd} |"
        )
    total_decisions = sum(summary.decision_count for summary in summaries)
    total_remits = sum(summary.remits for summary in summaries)
    total_retains = sum(summary.retains for summary in summaries)
    total_safe = sum(summary.safe_rounds for summary in summaries)
    total_settled = sum(summary.settled_rounds for summary in summaries)
    total_cost = sum((summary.total_cost_usd for summary in summaries), Decimal("0"))
    print()
    print(
        f"Pooled: {total_remits}/{total_decisions} remits; "
        f"{total_retains}/{total_decisions} retains; "
        f"{total_safe}/{total_settled} safe settled rounds; "
        f"${total_cost} total API cost."
    )


def main() -> None:
    """Run the authoritative EXP-030 event-log summary."""

    arguments = parse_arguments()
    run_directories = [Path(path) for path in arguments.run_dir]
    summaries = [summarize_run(run_dir=run_dir) for run_dir in run_directories]
    print_report(summaries=summaries)


if __name__ == "__main__":
    main()
