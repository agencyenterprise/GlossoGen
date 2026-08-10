#!/usr/bin/env python3
"""Summarize the frozen EXP-020 trajectories from authoritative JSONL events."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
RUNS = {
    "sonnet_5_independent": ("claude-sonnet-5", "independent", "1785958416"),
    "sonnet_5_covenant": ("claude-sonnet-5", "covenant", "1785958415"),
    "opus_5_independent": ("claude-opus-5", "independent", "1785960387"),
    "opus_5_covenant": ("claude-opus-5", "covenant", "1785960388"),
    "gpt_5_6_terra_independent": ("gpt-5.6-terra", "independent", "1785959541"),
    "gpt_5_6_terra_covenant": ("gpt-5.6-terra", "covenant", "1785959542"),
    "gpt_5_6_sol_independent": ("gpt-5.6-sol", "independent", "1785960847"),
    "gpt_5_6_sol_covenant": ("gpt-5.6-sol", "covenant", "1785960846"),
}


def load_events(run_id: str) -> list[dict]:
    path = (
        REPO_ROOT
        / "runs"
        / "bonded_team_production"
        / run_id
        / "bonded_team_production.jsonl"
    )
    return [json.loads(line) for line in path.read_text().splitlines()]


def summarize(model: str, arm: str, run_id: str) -> dict:
    events = load_events(run_id)
    by_type: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        event_type = event.get("event_type")
        if event_type:
            by_type[event_type].append(event)

    ended = by_type["simulation_ended"][-1]
    settled = by_type["team_production_order_settled"]
    submissions = by_type["team_production_zone_submitted"]
    attestations = by_type["team_production_attestation_submitted"]
    audits = by_type["team_production_audit_resolved"]

    profile_metrics: dict[str, dict[str, int]] = defaultdict(
        lambda: {"accepted": 0, "submitted": 0, "inspected": 0}
    )
    for outcome in settled:
        profile = profile_metrics[outcome["economic_profile"]]
        profile["accepted"] += outcome["accepted_assignments"]
        profile["submitted"] += outcome["submitted_assignments"]
        profile["inspected"] += outcome["inspected_assignments"]

    final_bond = None
    for event in events:
        if event.get("event_type") and "bond_balance" in event:
            final_bond = event["bond_balance"]

    last_case = by_type["team_production_case_started"][-1]
    expelled = {
        agent
        for audit in audits
        for agent in audit.get("expelled_agent_ids", [])
    }

    accepted = sum(item["accepted_assignments"] for item in settled)
    submitted = sum(item["submitted_assignments"] for item in settled)
    inspected = sum(item["inspected_assignments"] for item in settled)
    completed = sum(bool(item["completed"]) for item in settled)
    correct = sum(bool(item["completed"] and item["correct"]) for item in settled)

    completed_outcomes = [item for item in settled if item["completed"]]
    promised = sum(item["promised_total"] for item in completed_outcomes)
    paid = sum(item["paid_to_assignees"] for item in completed_outcomes)
    underpaid = sum(
        item["paid_to_assignees"] + 1e-9 < item["promised_total"]
        for item in completed_outcomes
    )

    return {
        "run_id": run_id,
        "model": model,
        "arm": arm,
        "completed_run": ended["reason"] == "scenario_complete",
        "rounds": len(by_type["round_advanced"]),
        "orders_completed": completed,
        "orders_correct": correct,
        "accepted_zones": accepted,
        "submitted_zones": submitted,
        "inspected_zones": inspected,
        "uninspected_submissions": sum(not item["inspected"] for item in submissions),
        "incorrect_zone_submissions": sum(not item["correct"] for item in submissions),
        "profiles": dict(sorted(profile_metrics.items())),
        "attestations": len(attestations),
        "false_attestations": sum(bool(item["false_claim"]) for item in attestations),
        "distributions_finalized": len(
            by_type["team_production_distribution_finalized"]
        ),
        "promised_on_completed_orders": round(promised, 2),
        "paid_on_completed_orders": round(paid, 2),
        "completed_orders_underpaid": underpaid,
        "audits": len(audits),
        "incorrect_audits": sum(not item["correct"] for item in audits),
        "refund_due": round(sum(item["refund_due"] for item in audits), 2),
        "refund_paid": round(sum(item["refund_paid"] for item in audits), 2),
        "sanctions": len(by_type["team_production_provider_sanctioned"]),
        "repairs": len(by_type["team_production_repair_submitted"]),
        "expelled_agents": sorted(expelled),
        "association_members_at_round_15_start": len(
            last_case.get("association_members", [])
        ),
        "final_bond_balance": final_bond,
        "public_messages": len(by_type["message_sent"]),
        "private_channels_created": len(
            by_type["team_production_private_channel_created"]
        ),
        "llm_responses": len(by_type["llm_response_received"]),
        "tool_calls": len(by_type["tool_call_invoked"]),
        "cost_usd": round(ended["total_cost_usd"], 8),
    }


def main() -> None:
    result = {
        role: summarize(model, arm, run_id)
        for role, (model, arm, run_id) in RUNS.items()
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
