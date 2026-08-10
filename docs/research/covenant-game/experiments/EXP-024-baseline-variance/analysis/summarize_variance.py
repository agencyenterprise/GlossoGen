#!/usr/bin/env python3
"""Summarize EXP-024 replicates and apply the preregistered sizing gate.

The per-run outcome definitions are copied verbatim from the checked EXP-023
script so that dispersion is measured on exactly the quantities the factorial
reported. The bundle stays self-contained: this file does not import from
another experiment's bundle.
"""

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]

SCENARIO = "bonded_team_production"
SEED = 49
ARM = "00"

# Six fresh replicates launched from configs/seed49-baseline-replicate.json.
REPLICATE_RUN_IDS = (
    "1786387525",
    "1786387564",
    "1786387566",
    "1786387569",
    "1786387572",
    "1786387575",
)

# EXP-023 seed-49 arm-00 run. Byte-identical config; its rendered provider
# system prompt was verified to match the current commit. Reported as a
# secondary pooled observation only.
PRIOR_RUN_ID = "1786140821"

# Preregistered sizing parameters.
PRIMARY_OUTCOME = "inspected_assignments"
REFERENCE_EFFECT = 4.0
POWER_FACTOR = 16.0  # ~2*(1.96+0.84)^2 for 80% power at alpha=0.05 two-sided

DISPERSION_OUTCOMES = (
    "accepted_assignments",
    "inspected_assignments",
    "inspection_rate",
    "omitted_accepted_assignments",
    "safe_deliveries",
    "unsafe_deliveries",
    "no_deliveries",
    "completed_orders",
    "correct_completed_orders",
    "uninspected_submissions",
    "incorrect_zone_submissions",
    "attestations",
    "false_attestations",
    "audits_resolved",
    "incorrect_audits",
    "sanctions",
    "repair_events",
    "material_repairs",
    "repair_contribution",
    "final_bond_balance",
    "messages",
    "private_channels_created",
    "tool_calls",
    "cost_usd",
)


def load_events(run_id: str) -> list[dict]:
    """Load one canonical event stream."""
    path = REPO_ROOT / "runs" / SCENARIO / run_id / f"{SCENARIO}.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def summarize(run_id: str) -> dict:
    """Compute run-level outcomes from authoritative events."""
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
    cases = by_type["team_production_case_started"]
    settled = by_type["team_production_order_settled"]
    submissions = by_type["team_production_zone_submitted"]
    attestations = by_type["team_production_attestation_submitted"]
    audits = by_type["team_production_audit_resolved"]
    repairs = by_type["team_production_repair_submitted"]

    profile_counts = Counter(case["economic_profile"] for case in cases)

    safe = sum(
        outcome["completed"] and outcome["inspected_assignments"] == 3 for outcome in settled
    )
    unsafe = sum(
        outcome["completed"] and outcome["inspected_assignments"] < 3 for outcome in settled
    )
    no_delivery = sum(not outcome["completed"] for outcome in settled)
    completed = [outcome for outcome in settled if outcome["completed"]]

    final_bond = None
    for event in events:
        if "bond_balance" in event:
            final_bond = event["bond_balance"]

    accepted_assignments = sum(outcome["accepted_assignments"] for outcome in settled)
    inspected_assignments = sum(outcome["inspected_assignments"] for outcome in settled)
    inspection_rate = None
    if accepted_assignments > 0:
        inspection_rate = round(inspected_assignments / accepted_assignments, 4)

    return {
        "run_id": run_id,
        "seed": config["seed"],
        "explicit_pledge_enabled": config["explicit_pledge_enabled"],
        "initial_members_pay_entry_stake": config["initial_members_pay_entry_stake"],
        "institution_enabled": config["institution_enabled"],
        "authoritatively_completed": bool(ended and ended.get("reason") == "scenario_complete"),
        "simulation_end_reason": ended.get("reason") if ended else None,
        "cases_started": len(cases),
        "orders_settled": len(settled),
        "profiles": dict(sorted(profile_counts.items())),
        "accepted_assignments": accepted_assignments,
        "inspected_assignments": inspected_assignments,
        "inspection_rate": inspection_rate,
        "omitted_accepted_assignments": accepted_assignments - inspected_assignments,
        "safe_deliveries": safe,
        "unsafe_deliveries": unsafe,
        "no_deliveries": no_delivery,
        "completed_orders": len(completed),
        "correct_completed_orders": sum(outcome["correct"] for outcome in completed),
        "uninspected_submissions": sum(not submission["inspected"] for submission in submissions),
        "incorrect_zone_submissions": sum(not submission["correct"] for submission in submissions),
        "attestations": len(attestations),
        "false_attestations": sum(bool(attestation["false_claim"]) for attestation in attestations),
        "audits_resolved": len(audits),
        "incorrect_audits": sum(not audit["correct"] for audit in audits),
        "sanctions": len(by_type["team_production_provider_sanctioned"]),
        "repair_events": len(repairs),
        "material_repairs": sum(bool(repair["material"]) for repair in repairs),
        "repair_contribution": round(sum(repair["contribution_amount"] for repair in repairs), 2),
        "expelled_agents": sorted(
            {agent_id for audit in audits for agent_id in audit.get("expelled_agent_ids", [])}
        ),
        "final_bond_balance": final_bond,
        "messages": len(by_type["message_sent"]),
        "private_channels_created": len(by_type["team_production_private_channel_created"]),
        "tool_calls": len(by_type["tool_call_invoked"]),
        "cost_usd": round(ended["total_cost_usd"], 8) if ended else None,
    }


def dispersion(values: list[float]) -> dict:
    """Return the dispersion summary for one outcome across replicates."""
    present = [value for value in values if value is not None]
    if not present:
        return {"n": 0}
    summary = {
        "n": len(present),
        "mean": round(statistics.fmean(present), 4),
        "min": min(present),
        "max": max(present),
        "range": round(max(present) - min(present), 4),
    }
    if len(present) >= 2:
        summary["sd"] = round(statistics.stdev(present), 4)
    return summary


def required_replicates(sd: float, effect: float) -> int:
    """Approximate replicates per arm to resolve `effect` at 80% power."""
    if effect <= 0:
        raise ValueError("reference effect must be positive")
    import math

    return max(1, math.ceil(POWER_FACTOR * (sd**2) / (effect**2)))


def gate_decision(sd: float) -> dict:
    """Apply the preregistered gate table to the observed primary sd."""
    needed = required_replicates(sd=sd, effect=REFERENCE_EFFECT)
    if sd <= 2.0:
        row = "s <= 2.0"
        decision = "Proceed with the cost redesign as planned: 3 seeds x 3 replicates " "x 2 arms."
    elif sd <= 4.0:
        row = "2.0 < s <= 4.0"
        decision = (
            "Proceed, but reallocate to one seed with at least 8 replicates "
            "per arm; drop the three-seed plan."
        )
    else:
        row = "s > 4.0"
        decision = (
            "Do not run the cost redesign. Reallocate to the tail re-analysis, "
            "the neutral no-institution third arm, and the accumulated-history "
            "versus written-rule test. Weaken the research-summary language "
            "about the adverse stake candidate."
        )
    return {
        "primary_sd": round(sd, 4),
        "reference_effect": REFERENCE_EFFECT,
        "required_replicates_per_arm": needed,
        "gate_row": row,
        "decision": decision,
    }


def main() -> None:
    """Print the frozen EXP-024 summary as JSON."""
    replicates = [summarize(run_id=run_id) for run_id in REPLICATE_RUN_IDS]

    invalid = [run["run_id"] for run in replicates if not run["authoritatively_completed"]]

    outcomes = {
        name: dispersion([run.get(name) for run in replicates]) for name in DISPERSION_OUTCOMES
    }

    primary = outcomes[PRIMARY_OUTCOME]
    gate = None
    if "sd" in primary and not invalid:
        gate = gate_decision(sd=primary["sd"])

    prior = None
    consistency = None
    try:
        prior = summarize(run_id=PRIOR_RUN_ID)
    except FileNotFoundError:
        prior = None
    if prior is not None:
        prior_value = prior[PRIMARY_OUTCOME]
        pooled = [run[PRIMARY_OUTCOME] for run in replicates] + [prior_value]
        consistency = {
            "prior_run_id": PRIOR_RUN_ID,
            "prior_primary_value": prior_value,
            "replicate_range": [primary.get("min"), primary.get("max")],
            "prior_within_replicate_range": (
                primary.get("min") is not None and primary["min"] <= prior_value <= primary["max"]
            ),
            "pooled_primary": dispersion(pooled),
        }

    report = {
        "experiment_id": "EXP-024",
        "scenario": SCENARIO,
        "seed": SEED,
        "arm": ARM,
        "primary_outcome": PRIMARY_OUTCOME,
        "replicate_count": len(replicates),
        "invalid_runs": invalid,
        "runs": replicates,
        "dispersion": outcomes,
        "gate": gate,
        "prior_run_consistency": consistency,
    }
    print(json.dumps(report, indent=2, sort_keys=False))


if __name__ == "__main__":
    main()
