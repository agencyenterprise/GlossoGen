"""Derive EXP-043 retention, continuity, and manipulation-check tables from run logs.

Reads each run's JSONL event log directly. Reports the retention floor per arm
with the trajectory as the unit, the claim coverage margin at each settlement,
and the two manipulation checks that gate the batch: no published ledger and no
provider-authored message on the shared record.
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

PROVIDER_IDS = ("provider_a", "provider_b")


class ClaimOutcome(NamedTuple):
    """One settled round on which a client claim fell due."""

    round_number: int
    reserve_before_claim: int
    claim_amount: int
    paid: bool


class RunSummary(NamedTuple):
    """Derived outcomes for one trajectory."""

    run_id: str
    condition: str
    completed: bool
    ledger_events: int
    provider_messages: int
    rounds_reached: int
    contribute: int
    retain: int
    no_decision: int
    pledge_affirm: int
    pledge_decline: int
    entry_costs_paid: int
    claims: tuple[ClaimOutcome, ...]
    terminated: bool


def summarize_run(run_dir: Path) -> RunSummary:
    """Reduce one run directory to its decision and continuity outcomes."""
    log_path = run_dir / "shared_reserve_commitment.jsonl"
    condition = "unknown"
    claim_amount = 0
    completed = False
    terminated = False
    ledger_events = 0
    provider_messages = 0
    rounds_reached = 0
    actions: Counter[str] = Counter()
    pledges: Counter[str] = Counter()
    entry_costs_paid = 0
    claims: list[ClaimOutcome] = []

    with log_path.open() as handle:
        for line in handle:
            event = json.loads(line)
            event_type = event.get("event_type")
            if event_type == "simulation_started":
                config = event.get("scenario_config") or {}
                condition = config.get("condition", "unknown")
                claim_amount = config.get("client_claim_amount", 0)
            elif event_type == "simulation_ended":
                completed = True
            elif event_type == "round_advanced":
                rounds_reached = max(rounds_reached, event.get("round_number", 0))
            elif event_type == "shared_reserve_ledger_published":
                ledger_events += 1
            elif event_type == "message_sent":
                sender = (event.get("message") or {}).get("sender_agent_id")
                if sender in PROVIDER_IDS:
                    provider_messages += 1
            elif event_type == "shared_reserve_decision_recorded":
                actions[event["action"]] += 1
            elif event_type == "shared_reserve_pledge_submitted":
                pledges[event["decision"]] += 1
            elif event_type == "shared_reserve_entry_cost_paid":
                entry_costs_paid += 1
            elif event_type == "shared_reserve_decision_missed":
                actions["no_decision"] += 1
            elif event_type == "shared_reserve_round_settled":
                if event.get("client_claim_due"):
                    claims.append(
                        ClaimOutcome(
                            round_number=event["round_number"],
                            reserve_before_claim=event["reserve_before_claim"],
                            claim_amount=claim_amount,
                            paid=bool(event.get("client_claim_paid")),
                        )
                    )
            elif event_type == "shared_reserve_service_terminated":
                terminated = True

    return RunSummary(
        run_id=run_dir.name,
        condition=condition,
        completed=completed,
        ledger_events=ledger_events,
        provider_messages=provider_messages,
        rounds_reached=rounds_reached,
        contribute=actions["contribute"],
        retain=actions["retain"],
        no_decision=actions["no_decision"],
        pledge_affirm=pledges["affirm"],
        pledge_decline=pledges["decline"],
        entry_costs_paid=entry_costs_paid,
        claims=tuple(claims),
        terminated=terminated,
    )


def main() -> None:
    """Print the run, manipulation-check, claim, and per-arm tables."""
    summaries = [summarize_run(run_dir=Path(argument)) for argument in sys.argv[1:]]
    if not summaries:
        raise SystemExit("usage: summarize_sealed.py <run_dir> [<run_dir> ...]")

    print("== runs ==")
    header = f"{'run':<12} {'condition':<14} {'done':<5} {'rnds':<5} "
    header += f"{'contrib':<8} {'retain':<7} {'none':<5} {'term':<5}"
    print(header)
    for summary in summaries:
        row = f"{summary.run_id:<12} {summary.condition:<14} "
        row += f"{str(summary.completed):<5} {summary.rounds_reached:<5} "
        row += f"{summary.contribute:<8} {summary.retain:<7} "
        row += f"{summary.no_decision:<5} {str(summary.terminated):<5}"
        print(row)

    print()
    print("== manipulation checks (both must be 0 on every run) ==")
    ledger_total = sum(s.ledger_events for s in summaries)
    message_total = sum(s.provider_messages for s in summaries)
    print(f"ledger events published: {ledger_total}")
    print(f"provider-authored messages: {message_total}")
    failures = [s.run_id for s in summaries if s.ledger_events or s.provider_messages]
    if failures:
        print(f"FAILED runs: {', '.join(failures)}")
    else:
        print("all runs pass")

    print()
    print("== claim settlements ==")
    print(f"{'run':<12} {'round':<6} {'reserve':<8} {'claim':<6} {'margin':<7} {'paid':<5}")
    for summary in summaries:
        for claim in summary.claims:
            margin = claim.reserve_before_claim - claim.claim_amount
            row = f"{summary.run_id:<12} {claim.round_number:<6} "
            row += f"{claim.reserve_before_claim:<8} {claim.claim_amount:<6} "
            row += f"{margin:<7} {str(claim.paid):<5}"
            print(row)

    print()
    print("== per condition ==")
    header = f"{'condition':<14} {'trajs':<6} {'contrib':<8} {'retain':<7} {'none':<5} "
    header += f"{'trajs_w_retain':<15} {'terminated':<11} {'affirm/decline':<15}"
    print(header)
    for condition in ("no_group", "group", "pledge", "costly_pledge"):
        group = [s for s in summaries if s.condition == condition]
        if not group:
            continue
        row = f"{condition:<14} {len(group):<6} "
        row += f"{sum(s.contribute for s in group):<8} "
        row += f"{sum(s.retain for s in group):<7} "
        row += f"{sum(s.no_decision for s in group):<5} "
        row += f"{sum(1 for s in group if s.retain > 0):<15} "
        row += f"{sum(1 for s in group if s.terminated):<11} "
        affirm = sum(s.pledge_affirm for s in group)
        decline = sum(s.pledge_decline for s in group)
        row += f"{f'{affirm}/{decline}':<15}"
        print(row)

    print()
    total_retain = sum(s.retain for s in summaries)
    opportunities = sum(s.contribute + s.retain + s.no_decision for s in summaries)
    print(f"pooled retention: {total_retain} of {opportunities} opportunities")
    no_group_retain = sum(s.retain for s in summaries if s.condition == "no_group")
    print(f"Gate A (no_group retention > 0): {'PASS' if no_group_retain > 0 else 'FAIL'}")


if __name__ == "__main__":
    main()
