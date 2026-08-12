"""Summarize the preregistered EXP-041 event-level outcomes.

Reports trajectory-level counts as the primary unit, the margin by which each
scheduled claim was covered, and the attribution of any service termination to
retention or to missed actions.
"""

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple


class ClaimOutcome(NamedTuple):
    """Coverage of one scheduled client claim."""

    round_number: int
    reserve_before_claim: int
    claim_amount: int
    paid: bool


class RunSummary(NamedTuple):
    """Event-derived outcomes for one simulation trajectory."""

    run_name: str
    condition: str
    completed: bool
    setup_events: int
    contributions: int
    retentions: int
    missed_actions: int
    pledge_affirms: int
    pledge_declines: int
    entry_cost_paid: float
    claims: tuple[ClaimOutcome, ...]
    terminated: bool
    service_active: bool
    api_cost_usd: float


def read_summary(run_dir: Path) -> RunSummary:
    """Read outcome events from one shared-reserve run directory."""

    event_path = run_dir / "shared_reserve_commitment.jsonl"
    condition = ""
    claim_amount = 0
    completed = False
    setup_events = 0
    contributions = 0
    retentions = 0
    missed_actions = 0
    pledge_affirms = 0
    pledge_declines = 0
    entry_cost_paid = 0.0
    claims: list[ClaimOutcome] = []
    terminated = False
    service_active = False
    api_cost_usd = 0.0

    with event_path.open(encoding="utf-8") as event_file:
        for line in event_file:
            event = json.loads(line)
            event_type = event["event_type"]
            if event_type == "simulation_started":
                scenario_config = event["scenario_config"]
                condition = str(scenario_config["condition"])
                claim_amount = int(scenario_config["client_claim_amount"])
            elif event_type == "shared_reserve_setup_published":
                setup_events += 1
            elif event_type == "shared_reserve_decision_recorded":
                action = event["action"]
                if action == "contribute":
                    contributions += 1
                elif action == "retain":
                    retentions += 1
            elif event_type == "shared_reserve_decision_missed":
                missed_actions += 1
            elif event_type == "shared_reserve_pledge_submitted":
                decision = event["decision"]
                if decision == "affirm":
                    pledge_affirms += 1
                elif decision == "decline":
                    pledge_declines += 1
            elif event_type == "shared_reserve_entry_cost_paid":
                entry_cost_paid += float(event["amount"])
            elif event_type == "shared_reserve_round_settled":
                if bool(event["client_claim_due"]):
                    claims.append(
                        ClaimOutcome(
                            round_number=int(event["round_number"]),
                            reserve_before_claim=int(event["reserve_before_claim"]),
                            claim_amount=claim_amount,
                            paid=bool(event["client_claim_paid"]),
                        )
                    )
                service_active = bool(event["service_active"])
            elif event_type == "shared_reserve_service_terminated":
                terminated = True
            elif event_type == "simulation_ended":
                completed = True
                api_cost_usd = float(event["total_cost_usd"])

    return RunSummary(
        run_name=run_dir.name,
        condition=condition,
        completed=completed,
        setup_events=setup_events,
        contributions=contributions,
        retentions=retentions,
        missed_actions=missed_actions,
        pledge_affirms=pledge_affirms,
        pledge_declines=pledge_declines,
        entry_cost_paid=entry_cost_paid,
        claims=tuple(claims),
        terminated=terminated,
        service_active=service_active,
        api_cost_usd=api_cost_usd,
    )


def print_run_table(summaries: Sequence[RunSummary]) -> None:
    """Print one machine-readable row per trajectory."""

    print(
        "run\tcondition\tcompleted\tsetup\tcontribute\tretain\tmissed\taffirm\tdecline"
        "\tentry_cost\tclaims_paid\tclaims_due\tterminated\tservice_active\tapi_cost"
    )
    for summary in sorted(summaries, key=lambda item: (item.condition, item.run_name)):
        claims_paid = sum(1 for claim in summary.claims if claim.paid)
        print(
            f"{summary.run_name}\t{summary.condition}\t{summary.completed}\t"
            f"{summary.setup_events}\t{summary.contributions}\t{summary.retentions}\t"
            f"{summary.missed_actions}\t{summary.pledge_affirms}\t{summary.pledge_declines}\t"
            f"{summary.entry_cost_paid:.1f}\t{claims_paid}\t{len(summary.claims)}\t"
            f"{summary.terminated}\t{summary.service_active}\t{summary.api_cost_usd:.7f}"
        )


def print_claim_margins(summaries: Sequence[RunSummary]) -> None:
    """Print how close each scheduled claim came to being uncovered."""

    print()
    print("run\tcondition\tclaim_round\treserve_before\tclaim_amount\tmargin\tpaid")
    for summary in sorted(summaries, key=lambda item: (item.condition, item.run_name)):
        for claim in summary.claims:
            margin = claim.reserve_before_claim - claim.claim_amount
            print(
                f"{summary.run_name}\t{summary.condition}\t{claim.round_number}\t"
                f"{claim.reserve_before_claim}\t{claim.claim_amount}\t{margin}\t{claim.paid}"
            )


def print_condition_table(summaries: Sequence[RunSummary]) -> None:
    """Print trajectory-level and pooled totals grouped by configured condition."""

    grouped: defaultdict[str, list[RunSummary]] = defaultdict(list)
    for summary in summaries:
        grouped[summary.condition].append(summary)

    print()
    print(
        "condition\truns\ttrajectories_with_retention\ttrajectories_terminated\tcontribute"
        "\tretain\tmissed\taffirm\tdecline\tentry_cost\tclaims_paid\tclaims_due\tapi_cost"
    )
    for condition in sorted(grouped):
        condition_runs = grouped[condition]
        print(
            f"{condition}\t{len(condition_runs)}\t"
            f"{sum(1 for item in condition_runs if item.retentions > 0)}\t"
            f"{sum(1 for item in condition_runs if item.terminated)}\t"
            f"{sum(item.contributions for item in condition_runs)}\t"
            f"{sum(item.retentions for item in condition_runs)}\t"
            f"{sum(item.missed_actions for item in condition_runs)}\t"
            f"{sum(item.pledge_affirms for item in condition_runs)}\t"
            f"{sum(item.pledge_declines for item in condition_runs)}\t"
            f"{sum(item.entry_cost_paid for item in condition_runs):.1f}\t"
            f"{sum(1 for item in condition_runs for claim in item.claims if claim.paid)}\t"
            f"{sum(len(item.claims) for item in condition_runs)}\t"
            f"{sum(item.api_cost_usd for item in condition_runs):.7f}"
        )


def main() -> None:
    """Parse configured run directories and print EXP-041 outcome tables."""

    parser = argparse.ArgumentParser()
    parser.add_argument("run_dirs", nargs="+", type=Path)
    arguments = parser.parse_args()
    summaries = [read_summary(run_dir=run_dir) for run_dir in arguments.run_dirs]
    print_run_table(summaries=summaries)
    print_claim_margins(summaries=summaries)
    print_condition_table(summaries=summaries)


if __name__ == "__main__":
    main()
