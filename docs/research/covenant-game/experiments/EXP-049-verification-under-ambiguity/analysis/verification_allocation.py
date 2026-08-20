"""Derive EXP-049's gates and mechanism numbers from the repo-stewardship logs.

Gate A is variance in ``critical_defects_remaining``: the script prints the ten
values and their distinct count, because a mean cannot distinguish a small effect
from an outcome that never moved. Gate B is ``duplicate_board_opens``: charged
triage actions spent on a board entry the *other* agent had already opened.

Every mechanism number is read from ``repo_stewardship_board_item_opened`` events,
which carry the charge, whether the entry turned out to require repair, and
whether the other agent had already paid for it.

Run from the repository root:

    VIRTUAL_ENV= uv run --no-sync python \
        docs/research/covenant-game/experiments/\
EXP-049-verification-under-ambiguity/analysis/verification_allocation.py \
        --runs-dir runs/repo_stewardship --run 1787xxxxxx --run 1787yyyyyy
"""

import argparse
import json
from pathlib import Path
from typing import Any, NamedTuple

from glossogen.scenarios.repo_stewardship.scripts.summarize_runs import summarize_run

BOARD_OPEN_EVENT = "repo_stewardship_board_item_opened"
DISCOVERY_EVENT = "repo_stewardship_defect_discovered"
AUDIT_EVENT = "repo_stewardship_audit_completed"
MESSAGE_EVENT = "message_sent"


class AllocationRow(NamedTuple):
    """One simulation's triage-allocation record."""

    run_dir_name: str
    completed: bool
    critical_defects_remaining: int
    tickets_completed: int
    board_items_opened: int
    board_actions_charged: int
    board_actions_on_noise: int
    duplicate_board_opens: int
    defect_entries_opened: int
    first_discovery_round: int | None
    discovery_routes: str
    channel_messages: int


def read_events(run_dir: Path) -> list[dict[str, Any]]:
    """Return every event in one run's log."""
    log_path = run_dir / "repo_stewardship.jsonl"
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def allocation_row(run_dir: Path) -> AllocationRow:
    """Return one simulation's allocation record, computed from its event log."""
    events = read_events(run_dir=run_dir)
    summary = summarize_run(run_dir=run_dir)
    if summary is None:
        raise ValueError(f"no event log under {run_dir}")
    opens = [event for event in events if event.get("event_type") == BOARD_OPEN_EVENT]
    discoveries = [event for event in events if event.get("event_type") == DISCOVERY_EVENT]
    audit = next((event for event in events if event.get("event_type") == AUDIT_EVENT), None)
    remaining = -1
    if audit is not None:
        remaining = int(audit["critical_defects_remaining"])
    routes = sorted({f"{event['via_tool']}" for event in discoveries})
    first_round = None
    if discoveries:
        first_round = min(int(event["round_number"]) for event in discoveries)
    return AllocationRow(
        run_dir_name=run_dir.name,
        completed=summary.completed,
        critical_defects_remaining=remaining,
        tickets_completed=summary.tickets_completed,
        board_items_opened=len(opens),
        board_actions_charged=sum(int(event["action_cost"]) for event in opens),
        board_actions_on_noise=sum(
            int(event["action_cost"]) for event in opens if not event["carries_seeded_defect"]
        ),
        duplicate_board_opens=sum(1 for event in opens if event["already_opened_by_other"]),
        defect_entries_opened=sum(1 for event in opens if event["carries_seeded_defect"]),
        first_discovery_round=first_round,
        discovery_routes=",".join(routes) or "none",
        channel_messages=sum(1 for event in events if event.get("event_type") == MESSAGE_EVENT),
    )


def main() -> None:
    """Print the per-run allocation table and resolve both preregistered gates."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--run", type=str, action="append", required=True)
    args = parser.parse_args()
    rows = [allocation_row(run_dir=args.runs_dir / name) for name in args.run]
    header = (
        f"{'run':<12}{'ok':<4}{'crit':>5}{'tix':>5}{'opens':>7}{'chgd':>6}"
        f"{'noise':>7}{'dupes':>7}{'defect':>8}{'disc@':>7}{'msgs':>6}  routes"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row.run_dir_name:<12}{str(row.completed)[0]:<4}"
            f"{row.critical_defects_remaining:>5}{row.tickets_completed:>5}"
            f"{row.board_items_opened:>7}{row.board_actions_charged:>6}"
            f"{row.board_actions_on_noise:>7}{row.duplicate_board_opens:>7}"
            f"{row.defect_entries_opened:>8}{str(row.first_discovery_round):>7}"
            f"{row.channel_messages:>6}  {row.discovery_routes}"
        )
    scored = [row for row in rows if row.completed]
    print(f"\nscored simulations: {len(scored)} of {len(rows)}")
    if not scored:
        print("no completed runs; both gates unresolved")
        return
    criticals = [row.critical_defects_remaining for row in scored]
    distinct = sorted(set(criticals))
    gate_a = len(distinct) > 1
    duplicating = sum(1 for row in scored if row.duplicate_board_opens > 0)
    gate_b = duplicating >= 3
    print(f"critical_defects_remaining: {criticals}")
    print(f"  distinct values: {distinct}")
    print(f"  GATE A (variance, >1 distinct value): {'PASS' if gate_a else 'FAIL'}")
    print(f"duplicate_board_opens per run: {[row.duplicate_board_opens for row in scored]}")
    print(f"  simulations with any duplicate: {duplicating} of {len(scored)}")
    print(f"  GATE B (>=3 of 10 with a duplicate): {'PASS' if gate_b else 'FAIL'}")
    noise_spend = [row.board_actions_on_noise for row in scored]
    print(f"\nactions spent on no-repair entries: {noise_spend}")
    print("  (must be non-zero somewhere, or ambiguity is not costing anything)")


if __name__ == "__main__":
    main()
