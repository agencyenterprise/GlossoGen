"""Derive EXP-025 action summaries from authoritative JSONL logs."""

import json
from pathlib import Path


RUNS = (
    ("covenant", 1, Path("runs/warehouse_commitment/1786417789/warehouse_commitment.jsonl")),
    ("no_group", 1, Path("runs/warehouse_commitment/1786417790/warehouse_commitment.jsonl")),
    ("pledge", 1, Path("runs/warehouse_commitment/1786417791/warehouse_commitment.jsonl")),
    ("group", 1, Path("runs/warehouse_commitment/1786417792/warehouse_commitment.jsonl")),
    ("covenant", 2, Path("runs/warehouse_commitment/1786418095/warehouse_commitment.jsonl")),
    ("pledge", 2, Path("runs/warehouse_commitment/1786418096/warehouse_commitment.jsonl")),
    ("no_group", 2, Path("runs/warehouse_commitment/1786418097/warehouse_commitment.jsonl")),
    ("group", 2, Path("runs/warehouse_commitment/1786418098/warehouse_commitment.jsonl")),
    ("covenant", 3, Path("runs/warehouse_commitment/1786418265/warehouse_commitment.jsonl")),
    ("group", 3, Path("runs/warehouse_commitment/1786418266/warehouse_commitment.jsonl")),
    ("pledge", 3, Path("runs/warehouse_commitment/1786418267/warehouse_commitment.jsonl")),
    ("no_group", 3, Path("runs/warehouse_commitment/1786418268/warehouse_commitment.jsonl")),
)


def load_events(path: Path) -> list[dict[str, object]]:
    """Load one run's JSONL events."""
    return [json.loads(line) for line in path.read_text().splitlines()]


def print_summary(condition: str, replicate: int, events: list[dict[str, object]]) -> None:
    """Print action, pledge, forfeiture, and completion facts for one arm."""
    actions = [
        event
        for event in events
        if event["event_type"] == "warehouse_commitment_action_chosen"
    ]
    pledges = [
        event
        for event in events
        if event["event_type"] == "warehouse_commitment_pledge_submitted"
    ]
    settled = [
        event
        for event in events
        if event["event_type"] == "warehouse_commitment_round_settled"
    ]
    completed = [event for event in settled if event["completed"]]
    inspections = [event for event in actions if event["inspected"]]
    shortcuts = [event for event in actions if not event["inspected"]]
    joint_inspections = [event for event in completed if event["joint_inspection"]]
    forfeiture = sum(float(event["forfeiture_paid"]) for event in actions)
    ended = [event for event in events if event["event_type"] == "simulation_ended"]

    print(
        json.dumps(
            {
                "condition": condition,
                "replicate": replicate,
                "completed": len(ended) == 1,
                "action_count": len(actions),
                "inspections": len(inspections),
                "shortcuts": len(shortcuts),
                "completed_rounds": len(completed),
                "joint_inspection_rounds": len(joint_inspections),
                "pledge_decisions": [event["decision"] for event in pledges],
                "forfeiture_paid": forfeiture,
            },
            sort_keys=True,
        )
    )


def main() -> None:
    """Produce a machine-readable summary for all twelve pilot trajectories."""
    for condition, replicate, path in RUNS:
        print_summary(
            condition=condition,
            replicate=replicate,
            events=load_events(path=path),
        )


if __name__ == "__main__":
    main()
