"""Summarize the preregistered EXP-040 event-level outcomes."""

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple


class RunSummary(NamedTuple):
    """Event-derived outcomes for one completed simulation trajectory."""

    run_name: str
    condition: str
    setup_events: int
    contributions: int
    retentions: int
    missed_actions: int
    pledge_affirms: int
    pledge_declines: int
    entry_cost_paid: float
    claims_due: int
    claims_paid: int
    service_active: bool
    api_cost_usd: float


def read_summary(run_dir: Path) -> RunSummary:
    """Read outcome events from one shared-reserve run directory."""

    event_path = run_dir / "shared_reserve_commitment.jsonl"
    condition = ""
    setup_events = 0
    contributions = 0
    retentions = 0
    missed_actions = 0
    pledge_affirms = 0
    pledge_declines = 0
    entry_cost_paid = 0.0
    claims_due = 0
    claims_paid = 0
    service_active = False
    api_cost_usd = 0.0

    with event_path.open(encoding="utf-8") as event_file:
        for line in event_file:
            event = json.loads(line)
            event_type = event["event_type"]
            if event_type == "simulation_started":
                scenario_config = event["scenario_config"]
                condition = str(scenario_config["condition"])
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
                claim_due = bool(event["client_claim_due"])
                if claim_due:
                    claims_due += 1
                    claim_paid = bool(event["client_claim_paid"])
                    if claim_paid:
                        claims_paid += 1
                service_active = bool(event["service_active"])
            elif event_type == "simulation_ended":
                api_cost_usd = float(event["total_cost_usd"])

    return RunSummary(
        run_name=run_dir.name,
        condition=condition,
        setup_events=setup_events,
        contributions=contributions,
        retentions=retentions,
        missed_actions=missed_actions,
        pledge_affirms=pledge_affirms,
        pledge_declines=pledge_declines,
        entry_cost_paid=entry_cost_paid,
        claims_due=claims_due,
        claims_paid=claims_paid,
        service_active=service_active,
        api_cost_usd=api_cost_usd,
    )


def print_run_table(summaries: Sequence[RunSummary]) -> None:
    """Print one machine-readable row per trajectory."""

    print(
        "run\tcondition\tsetup\tcontribute\tretain\tmissed\taffirm\tdecline"
        "\tentry_cost\tclaims_paid\tclaims_due\tservice_active\tapi_cost"
    )
    for summary in sorted(summaries, key=lambda item: (item.condition, item.run_name)):
        print(
            f"{summary.run_name}\t{summary.condition}\t{summary.setup_events}\t"
            f"{summary.contributions}\t"
            f"{summary.retentions}\t{summary.missed_actions}\t{summary.pledge_affirms}\t"
            f"{summary.pledge_declines}\t{summary.entry_cost_paid:.1f}\t"
            f"{summary.claims_paid}\t{summary.claims_due}\t{summary.service_active}\t"
            f"{summary.api_cost_usd:.7f}"
        )


def print_condition_table(summaries: Sequence[RunSummary]) -> None:
    """Print event totals grouped by configured condition."""

    grouped: defaultdict[str, list[RunSummary]] = defaultdict(list)
    for summary in summaries:
        grouped[summary.condition].append(summary)

    print()
    print(
        "condition\truns\tsetup\tcontribute\tretain\tmissed\taffirm\tdecline"
        "\tentry_cost\tclaims_paid\tclaims_due\tactive_runs\tapi_cost"
    )
    for condition in sorted(grouped):
        condition_runs = grouped[condition]
        print(
            f"{condition}\t{len(condition_runs)}\t"
            f"{sum(item.setup_events for item in condition_runs)}\t"
            f"{sum(item.contributions for item in condition_runs)}\t"
            f"{sum(item.retentions for item in condition_runs)}\t"
            f"{sum(item.missed_actions for item in condition_runs)}\t"
            f"{sum(item.pledge_affirms for item in condition_runs)}\t"
            f"{sum(item.pledge_declines for item in condition_runs)}\t"
            f"{sum(item.entry_cost_paid for item in condition_runs):.1f}\t"
            f"{sum(item.claims_paid for item in condition_runs)}\t"
            f"{sum(item.claims_due for item in condition_runs)}\t"
            f"{sum(item.service_active for item in condition_runs)}\t"
            f"{sum(item.api_cost_usd for item in condition_runs):.7f}"
        )


def main() -> None:
    """Parse configured run directories and print EXP-040 outcome tables."""

    parser = argparse.ArgumentParser()
    parser.add_argument("run_dirs", nargs="+", type=Path)
    arguments = parser.parse_args()
    summaries = [read_summary(run_dir=run_dir) for run_dir in arguments.run_dirs]
    print_run_table(summaries=summaries)
    print_condition_table(summaries=summaries)


if __name__ == "__main__":
    main()
