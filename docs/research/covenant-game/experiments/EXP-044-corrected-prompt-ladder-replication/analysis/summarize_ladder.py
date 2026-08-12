"""Derive EXP-044 defection, continuity, and gate verdicts from run logs.

Reads each run's JSONL event log directly and reports the per-arm defection
table with the trajectory as the unit, the batch-1 reference values from
EXP-038 and EXP-039, and the two preregistered gates.
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

PROVIDER_IDS = ("provider_a", "provider_b")
ARMS = ("no_group", "group", "pledge", "costly_pledge")

BATCH_ONE_RETAIN = {"no_group": 12, "group": 27, "pledge": 0, "costly_pledge": 0}
BATCH_ONE_OPPORTUNITIES = 96


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
    rounds_reached: int
    contribute: int
    retain: int
    retain_slack: int
    retain_exposed: int
    no_decision: int
    provider_messages: int
    ledger_events: int
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
    rounds_reached = 0
    provider_messages = 0
    ledger_events = 0
    entry_costs_paid = 0
    actions: Counter[str] = Counter()
    pledges: Counter[str] = Counter()
    claims: list[ClaimOutcome] = []
    retains_by_round: Counter[int] = Counter()
    settled_reserve: dict[int, int] = {}

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
                if event["action"] == "retain":
                    retains_by_round[event["round_number"]] += 1
            elif event_type == "shared_reserve_decision_missed":
                actions["no_decision"] += 1
            elif event_type == "shared_reserve_pledge_submitted":
                pledges[event["decision"]] += 1
            elif event_type == "shared_reserve_entry_cost_paid":
                entry_costs_paid += 1
            elif event_type == "shared_reserve_round_settled":
                # Exposure must be read from the reserve as the round's decisions
                # left it, before any claim is deducted. Using the post-claim
                # balance instead flags every claim round as exposed, because a
                # covered claim legitimately drains the reserve.
                settled_reserve[event["round_number"]] = event["reserve_before_claim"]
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

    retain_exposed = 0
    for round_number, count in retains_by_round.items():
        reserve = settled_reserve.get(round_number)
        if reserve is not None and reserve < claim_amount:
            retain_exposed += count

    return RunSummary(
        run_id=run_dir.name,
        condition=condition,
        completed=completed,
        rounds_reached=rounds_reached,
        contribute=actions["contribute"],
        retain=actions["retain"],
        retain_slack=actions["retain"] - retain_exposed,
        retain_exposed=retain_exposed,
        no_decision=actions["no_decision"],
        provider_messages=provider_messages,
        ledger_events=ledger_events,
        pledge_affirm=pledges["affirm"],
        pledge_decline=pledges["decline"],
        entry_costs_paid=entry_costs_paid,
        claims=tuple(claims),
        terminated=terminated,
    )


def main() -> None:
    """Print the run table, the per-arm table against batch 1, and the gates."""
    summaries = [summarize_run(run_dir=Path(argument)) for argument in sys.argv[1:]]
    if not summaries:
        raise SystemExit("usage: summarize_ladder.py <run_dir> [<run_dir> ...]")

    print("== runs ==")
    header = f"{'run':<12} {'condition':<14} {'done':<5} {'rnds':<5} "
    header += f"{'contrib':<8} {'retain':<7} {'none':<5} {'msgs':<5} {'term':<5}"
    print(header)
    for summary in sorted(summaries, key=lambda s: (s.condition, s.run_id)):
        row = f"{summary.run_id:<12} {summary.condition:<14} "
        row += f"{str(summary.completed):<5} {summary.rounds_reached:<5} "
        row += f"{summary.contribute:<8} {summary.retain:<7} {summary.no_decision:<5} "
        row += f"{summary.provider_messages:<5} {str(summary.terminated):<5}"
        print(row)

    incomplete = [s.run_id for s in summaries if not s.completed]
    if incomplete:
        print(f"\nWARNING incomplete runs excluded from gates: {', '.join(incomplete)}")
    usable = [s for s in summaries if s.completed]

    print()
    print("== per arm, against batch 1 (EXP-038 + EXP-039) ==")
    header = f"{'arm':<14} {'trajs':<6} {'opps':<6} {'retain':<7} {'rate':<8} "
    header += f"{'slack':<7} {'exposed':<8} {'trajs_w_ret':<12} {'batch1_rate':<12} "
    header += f"{'none':<5} {'term':<5}"
    print(header)
    trajectories_with_defection: dict[str, int] = {}
    exposed_by_arm: dict[str, int] = {}
    for arm in ARMS:
        group = [s for s in usable if s.condition == arm]
        if not group:
            continue
        opportunities = sum(s.contribute + s.retain + s.no_decision for s in group)
        retain = sum(s.retain for s in group)
        with_defection = sum(1 for s in group if s.retain > 0)
        trajectories_with_defection[arm] = with_defection
        exposed_by_arm[arm] = sum(s.retain_exposed for s in group)
        rate = 0.0
        if opportunities:
            rate = 100.0 * retain / opportunities
        batch_one = 100.0 * BATCH_ONE_RETAIN[arm] / BATCH_ONE_OPPORTUNITIES
        row = f"{arm:<14} {len(group):<6} {opportunities:<6} {retain:<7} "
        row += f"{rate:>6.1f}%  {sum(s.retain_slack for s in group):<7} "
        row += f"{exposed_by_arm[arm]:<8} {f'{with_defection}/{len(group)}':<12} "
        row += f"{batch_one:>9.1f}%   {sum(s.no_decision for s in group):<5} "
        row += f"{sum(1 for s in group if s.terminated):<5}"
        print(row)
    print()
    print("  slack   = retention in a round that settled with the reserve still")
    print("            able to absorb a claim; the service was never exposed by it.")
    print("  exposed = retention in a round that settled below the claim amount.")

    print()
    print("== pledge uptake and claims ==")
    for arm in ("pledge", "costly_pledge"):
        group = [s for s in usable if s.condition == arm]
        if not group:
            continue
        affirm = sum(s.pledge_affirm for s in group)
        decline = sum(s.pledge_decline for s in group)
        paid = sum(s.entry_costs_paid for s in group)
        print(f"{arm:<14} affirm={affirm} decline={decline} entry_costs_paid={paid}")
    all_claims = [claim for summary in usable for claim in summary.claims]
    unpaid = [claim for claim in all_claims if not claim.paid]
    print(f"claims due={len(all_claims)} paid={len(all_claims) - len(unpaid)} unpaid={len(unpaid)}")
    for summary in usable:
        for claim in summary.claims:
            if not claim.paid:
                print(
                    f"  UNPAID {summary.run_id} round={claim.round_number} "
                    f"reserve={claim.reserve_before_claim} claim={claim.claim_amount}"
                )

    print()
    print("== preregistered gates ==")
    no_group_retain = sum(s.retain for s in usable if s.condition == "no_group")
    gate_a = no_group_retain > 0
    print(
        f"Gate A (no_group produced at least one retain): "
        f"{'PASS' if gate_a else 'FAIL'} ({no_group_retain} retentions)"
    )
    exposed_total = sum(exposed_by_arm.values())
    print(f"  of which exposed the service across all arms: {exposed_total}")
    if gate_a and exposed_total == 0:
        print("  CAVEAT: Gate A passes on slack harvesting alone. Every retention")
        print("  in this batch left the reserve able to absorb a claim, so the gate")
        print("  did not detect free-riding, which is the construct it was written")
        print("  for. Read the pass as instrument activation, not as a defection")
        print("  baseline comparable to the human study's non-contribution rate.")
    if not gate_a:
        print("Gate B: not evaluated — a control pinned at zero leaves no headroom.")
        print("Gate C: FIRED. The corrected prompt does not restore variance.")
        print("        Authorized next step is the verbatim re-run at e393852.")
        return
    baseline = trajectories_with_defection.get("no_group", 0)
    group = trajectories_with_defection.get("group", 0)
    pledge = trajectories_with_defection.get("pledge", 0)
    costly = trajectories_with_defection.get("costly_pledge", 0)
    checks = (
        ("group >= no_group", group >= baseline),
        ("pledge < group", pledge < group),
        ("costly_pledge < group", costly < group),
    )
    for label, passed in checks:
        print(f"  {label}: {'PASS' if passed else 'FAIL'}")
    verdict = all(passed for _, passed in checks)
    print(f"Gate B (batch-1 ordering reproduced): {'PASS' if verdict else 'FAIL'}")


if __name__ == "__main__":
    main()
