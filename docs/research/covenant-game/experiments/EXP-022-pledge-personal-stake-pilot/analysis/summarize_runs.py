#!/usr/bin/env python3
"""Summarize EXP-022 from authoritative team-production event logs."""

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
RUNS = {
    "no_pledge_no_cost": "1786139285",
    "pledge_and_cost": "1786139286",
    "cost_only": "1786139287",
    "pledge_only": "1786139288",
}


def load_events(run_id: str) -> list[dict]:
    """Load one run's canonical JSONL event stream."""
    path = (
        REPO_ROOT
        / "runs"
        / "bonded_team_production"
        / run_id
        / "bonded_team_production.jsonl"
    )
    return [json.loads(line) for line in path.read_text().splitlines()]


def summarize(arm: str, run_id: str) -> dict:
    """Compute the preregistered activation and behavioral measures for one arm."""
    events = load_events(run_id=run_id)
    by_type: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        event_type = event.get("event_type")
        if event_type:
            by_type[event_type].append(event)

    started = by_type["simulation_started"][0]
    config = started["scenario_config"]
    ended_events = by_type["simulation_ended"]
    ended = ended_events[-1] if ended_events else None
    settled = by_type["team_production_order_settled"]
    submissions = by_type["team_production_zone_submitted"]
    attestations = by_type["team_production_attestation_submitted"]
    pledges = by_type["team_production_pledge_submitted"]
    stakes = by_type["team_production_initial_stake_charged"]
    audits = by_type["team_production_audit_resolved"]
    repairs = by_type["team_production_repair_submitted"]
    cases = by_type["team_production_case_started"]

    profiles = Counter(case["economic_profile"] for case in cases)
    profile_outcomes: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "orders": 0,
            "accepted_assignments": 0,
            "inspected_assignments": 0,
            "safe_deliveries": 0,
            "unsafe_deliveries": 0,
            "no_deliveries": 0,
        }
    )
    for outcome in settled:
        profile = profile_outcomes[outcome["economic_profile"]]
        profile["orders"] += 1
        profile["accepted_assignments"] += outcome["accepted_assignments"]
        profile["inspected_assignments"] += outcome["inspected_assignments"]
        if not outcome["completed"]:
            profile["no_deliveries"] += 1
        elif outcome["inspected_assignments"] == 3:
            profile["safe_deliveries"] += 1
        else:
            profile["unsafe_deliveries"] += 1
    safe = sum(
        outcome["completed"] and outcome["inspected_assignments"] == 3
        for outcome in settled
    )
    unsafe = sum(
        outcome["completed"] and outcome["inspected_assignments"] < 3
        for outcome in settled
    )
    no_delivery = sum(not outcome["completed"] for outcome in settled)
    completed_outcomes = [outcome for outcome in settled if outcome["completed"]]

    pledge_decisions = Counter(pledge["decision"] for pledge in pledges)
    stake_amounts = Counter(stake["stake_amount"] for stake in stakes)
    starting_balances = Counter(stake["balance_after"] for stake in stakes)

    final_bond = None
    for event in events:
        if "bond_balance" in event:
            final_bond = event["bond_balance"]

    summary = {
        "arm": arm,
        "run_id": run_id,
        "explicit_pledge_enabled": config["explicit_pledge_enabled"],
        "initial_members_pay_entry_stake": config[
            "initial_members_pay_entry_stake"
        ],
        "authoritatively_completed": bool(
            ended and ended.get("reason") == "scenario_complete"
        ),
        "simulation_end_reason": ended.get("reason") if ended else None,
        "cases_started": len(cases),
        "orders_settled": len(settled),
        "profiles": dict(sorted(profiles.items())),
        "profile_outcomes": dict(sorted(profile_outcomes.items())),
        "pledge_events": len(pledges),
        "pledge_agents": sorted({pledge["agent_id"] for pledge in pledges}),
        "pledge_decisions": dict(sorted(pledge_decisions.items())),
        "stake_events": len(stakes),
        "stake_agents": sorted({stake["agent_id"] for stake in stakes}),
        "stake_amounts": {str(key): value for key, value in stake_amounts.items()},
        "post_stake_starting_balances": {
            str(key): value for key, value in starting_balances.items()
        },
        "accepted_assignments": sum(
            outcome["accepted_assignments"] for outcome in settled
        ),
        "submitted_assignments": sum(
            outcome["submitted_assignments"] for outcome in settled
        ),
        "inspected_assignments": sum(
            outcome["inspected_assignments"] for outcome in settled
        ),
        "omitted_accepted_assignments": sum(
            outcome["accepted_assignments"] - outcome["inspected_assignments"]
            for outcome in settled
        ),
        "safe_deliveries": safe,
        "unsafe_deliveries": unsafe,
        "no_deliveries": no_delivery,
        "completed_orders": len(completed_outcomes),
        "correct_completed_orders": sum(
            outcome["correct"] for outcome in completed_outcomes
        ),
        "uninspected_submissions": sum(
            not submission["inspected"] for submission in submissions
        ),
        "incorrect_zone_submissions": sum(
            not submission["correct"] for submission in submissions
        ),
        "attestations": len(attestations),
        "false_attestations": sum(
            bool(attestation["false_claim"]) for attestation in attestations
        ),
        "promised_on_completed_orders": round(
            sum(outcome["promised_total"] for outcome in completed_outcomes), 2
        ),
        "paid_on_completed_orders": round(
            sum(outcome["paid_to_assignees"] for outcome in completed_outcomes), 2
        ),
        "completed_orders_underpaid": sum(
            outcome["paid_to_assignees"] + 1e-9 < outcome["promised_total"]
            for outcome in completed_outcomes
        ),
        "audits_resolved": len(audits),
        "incorrect_audits": sum(not audit["correct"] for audit in audits),
        "refund_due": round(sum(audit["refund_due"] for audit in audits), 2),
        "refund_paid": round(sum(audit["refund_paid"] for audit in audits), 2),
        "sanctions": len(by_type["team_production_provider_sanctioned"]),
        "repair_events": len(repairs),
        "material_repairs": sum(bool(repair["material"]) for repair in repairs),
        "repair_contribution": round(
            sum(repair["contribution_amount"] for repair in repairs), 2
        ),
        "expelled_agents": sorted(
            {
                agent_id
                for audit in audits
                for agent_id in audit.get("expelled_agent_ids", [])
            }
        ),
        "membership_decisions": len(
            by_type["team_production_membership_decision_submitted"]
        ),
        "association_members_at_final_case_start": len(
            cases[-1]["association_members"]
        ),
        "final_bond_balance": final_bond,
        "messages": len(by_type["message_sent"]),
        "private_channels_created": len(
            by_type["team_production_private_channel_created"]
        ),
        "llm_responses": len(by_type["llm_response_received"]),
        "tool_calls": len(by_type["tool_call_invoked"]),
        "cost_usd": round(ended["total_cost_usd"], 8) if ended else None,
    }
    return summary


def activation_gates(results: dict[str, dict]) -> dict:
    """Apply the pilot gates exactly as preregistered."""
    all_completed = all(
        result["authoritatively_completed"]
        and result["cases_started"] == 6
        and result["orders_settled"] == 6
        and result["profiles"]
        == {"effort_favorable": 2, "marginal": 2, "shirking_tempting": 2}
        for result in results.values()
    )
    pledge_arms = [result for result in results.values() if result["explicit_pledge_enabled"]]
    no_pledge_arms = [
        result for result in results.values() if not result["explicit_pledge_enabled"]
    ]
    pledge_activated = all(
        result["pledge_events"] == 6
        and len(result["pledge_agents"]) == 6
        and result["pledge_decisions"].get("affirm", 0) >= 5
        for result in pledge_arms
    ) and all(result["pledge_events"] == 0 for result in no_pledge_arms)

    cost_arms = [
        result
        for result in results.values()
        if result["initial_members_pay_entry_stake"]
    ]
    no_cost_arms = [
        result
        for result in results.values()
        if not result["initial_members_pay_entry_stake"]
    ]
    cost_activated = all(
        result["stake_events"] == 6
        and len(result["stake_agents"]) == 6
        and result["stake_amounts"] == {"30.0": 6}
        and result["post_stake_starting_balances"] == {"270.0": 6}
        for result in cost_arms
    ) and all(result["stake_events"] == 0 for result in no_cost_arms)

    pooled_inspected = sum(
        result["inspected_assignments"] for result in results.values()
    )
    pooled_omitted = sum(
        result["omitted_accepted_assignments"] for result in results.values()
    )
    distinct_outcomes = {
        (result["inspected_assignments"], result["safe_deliveries"])
        for result in results.values()
    }
    useful_variation = (
        pooled_inspected > 0 and pooled_omitted > 0 and len(distinct_outcomes) >= 2
    )
    return {
        "execution_valid": all_completed,
        "pledge_activated": pledge_activated,
        "cost_activated": cost_activated,
        "useful_behavioral_variation": useful_variation,
        "pooled_inspected_assignments": pooled_inspected,
        "pooled_omitted_accepted_assignments": pooled_omitted,
        "distinct_inspection_safe_delivery_outcomes": sorted(distinct_outcomes),
        "advance_to_full_factorial": (
            all_completed and pledge_activated and cost_activated and useful_variation
        ),
    }


def main() -> None:
    """Print arm summaries and the preregistered gate decision as JSON."""
    results = {
        arm: summarize(arm=arm, run_id=run_id) for arm, run_id in RUNS.items()
    }
    payload = {"runs": results, "gates": activation_gates(results=results)}
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
