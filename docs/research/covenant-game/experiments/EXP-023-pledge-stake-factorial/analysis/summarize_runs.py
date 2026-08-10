#!/usr/bin/env python3
"""Summarize EXP-023 and compute preregistered factorial contrasts."""

import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
EXPECTED_SEEDS = {49, 50}
RUNS = {
    "seed49_00": (49, "00", "1786140821"),
    "seed49_01": (49, "01", "1786140822"),
    "seed49_10": (49, "10", "1786140823"),
    "seed49_11": (49, "11", "1786140824"),
    "seed50_00": (50, "00", "1786141680"),
    "seed50_01": (50, "01", "1786141681"),
    "seed50_10": (50, "10", "1786141679"),
    "seed50_11": (50, "11", "1786141678"),
}


def load_events(run_id: str) -> list[dict]:
    """Load one canonical event stream."""
    path = (
        REPO_ROOT
        / "runs"
        / "bonded_team_production"
        / run_id
        / "bonded_team_production.jsonl"
    )
    return [json.loads(line) for line in path.read_text().splitlines()]


def summarize(seed: int, arm: str, run_id: str) -> dict:
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
    pledges = by_type["team_production_pledge_submitted"]
    stakes = by_type["team_production_initial_stake_charged"]
    audits = by_type["team_production_audit_resolved"]
    repairs = by_type["team_production_repair_submitted"]

    profile_counts = Counter(case["economic_profile"] for case in cases)
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
    completed = [outcome for outcome in settled if outcome["completed"]]

    final_bond = None
    for event in events:
        if "bond_balance" in event:
            final_bond = event["bond_balance"]

    accepted_assignments = sum(
        outcome["accepted_assignments"] for outcome in settled
    )
    inspected_assignments = sum(
        outcome["inspected_assignments"] for outcome in settled
    )
    inspection_rate = None
    if accepted_assignments > 0:
        inspection_rate = round(inspected_assignments / accepted_assignments, 4)

    return {
        "seed": seed,
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
        "profiles": dict(sorted(profile_counts.items())),
        "profile_outcomes": dict(sorted(profile_outcomes.items())),
        "pledge_events": len(pledges),
        "pledge_agents": sorted({pledge["agent_id"] for pledge in pledges}),
        "pledge_decisions": dict(
            sorted(Counter(pledge["decision"] for pledge in pledges).items())
        ),
        "stake_events": len(stakes),
        "stake_agents": sorted({stake["agent_id"] for stake in stakes}),
        "stake_amounts": dict(
            sorted(Counter(stake["stake_amount"] for stake in stakes).items())
        ),
        "post_stake_balances": dict(
            sorted(Counter(stake["balance_after"] for stake in stakes).items())
        ),
        "accepted_assignments": accepted_assignments,
        "submitted_assignments": sum(
            outcome["submitted_assignments"] for outcome in settled
        ),
        "inspected_assignments": inspected_assignments,
        "inspection_rate": inspection_rate,
        "omitted_accepted_assignments": sum(
            outcome["accepted_assignments"] - outcome["inspected_assignments"]
            for outcome in settled
        ),
        "safe_deliveries": safe,
        "unsafe_deliveries": unsafe,
        "no_deliveries": no_delivery,
        "completed_orders": len(completed),
        "correct_completed_orders": sum(outcome["correct"] for outcome in completed),
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
            sum(outcome["promised_total"] for outcome in completed), 2
        ),
        "paid_on_completed_orders": round(
            sum(outcome["paid_to_assignees"] for outcome in completed), 2
        ),
        "completed_orders_underpaid": sum(
            outcome["paid_to_assignees"] + 1e-9 < outcome["promised_total"]
            for outcome in completed
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
        "association_members_at_final_case_start": (
            len(cases[-1]["association_members"]) if cases else None
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


def factorial_contrast(values: dict[str, float]) -> dict[str, float]:
    """Compute the preregistered 2 x 2 main effects and interaction."""
    return {
        "pledge_main_effect": round(
            ((values["10"] - values["00"]) + (values["11"] - values["01"]))
            / 2,
            4,
        ),
        "cost_main_effect": round(
            ((values["01"] - values["00"]) + (values["11"] - values["10"]))
            / 2,
            4,
        ),
        "interaction": round(
            values["11"] - values["10"] - values["01"] + values["00"],
            4,
        ),
    }


def contrasts(results: dict[str, dict]) -> dict[str, dict]:
    """Compute factorial contrasts independently for each complete seed."""
    metrics = (
        "inspected_assignments",
        "inspection_rate",
        "safe_deliveries",
        "unsafe_deliveries",
        "no_deliveries",
        "correct_completed_orders",
    )
    output: dict[str, dict] = {}
    for seed in sorted(EXPECTED_SEEDS):
        arm_results = {
            result["arm"]: result
            for result in results.values()
            if result["seed"] == seed
        }
        if set(arm_results) != {"00", "01", "10", "11"}:
            continue
        output[str(seed)] = {
            metric: factorial_contrast(
                values={arm: arm_results[arm][metric] for arm in arm_results}
            )
            for metric in metrics
        }
    return output


def same_nonzero_sign(first: float, second: float) -> bool:
    """Return whether two contrasts are non-zero and share a sign."""
    return first != 0 and second != 0 and (first > 0) == (second > 0)


def gates(results: dict[str, dict], effect_contrasts: dict[str, dict]) -> dict:
    """Apply execution, manipulation, and repeatability gates."""
    expected_profiles = {
        "effort_favorable": 5,
        "marginal": 5,
        "shirking_tempting": 5,
    }
    execution_valid = (
        {result["seed"] for result in results.values()} == EXPECTED_SEEDS
        and len(results) == 8
        and all(
            result["authoritatively_completed"]
            and result["cases_started"] == 15
            and result["orders_settled"] == 15
            and result["profiles"] == expected_profiles
            for result in results.values()
        )
    )
    pledge_valid = all(
        (
            result["pledge_events"] == 6
            and len(result["pledge_agents"]) == 6
            and result["pledge_decisions"].get("affirm", 0) >= 5
        )
        if result["explicit_pledge_enabled"]
        else result["pledge_events"] == 0
        for result in results.values()
    )
    cost_valid = all(
        (
            result["stake_events"] == 6
            and len(result["stake_agents"]) == 6
            and result["stake_amounts"] == {30.0: 6}
            and result["post_stake_balances"] == {270.0: 6}
        )
        if result["initial_members_pay_entry_stake"]
        else result["stake_events"] == 0
        for result in results.values()
    )

    candidates = {}
    if set(effect_contrasts) == {"49", "50"}:
        for effect in (
            "pledge_main_effect",
            "cost_main_effect",
            "interaction",
        ):
            first = effect_contrasts["49"]["inspected_assignments"][effect]
            second = effect_contrasts["50"]["inspected_assignments"][effect]
            candidates[effect] = {
                "seed49": first,
                "seed50": second,
                "same_nonzero_sign": same_nonzero_sign(first=first, second=second),
            }
    return {
        "execution_valid": execution_valid,
        "pledge_manipulation_valid": pledge_valid,
        "cost_manipulation_valid": cost_valid,
        "inspection_mechanism_candidates": candidates,
    }


def main() -> None:
    """Write JSON summaries, contrasts, and preregistered gates to stdout."""
    results = {
        role: summarize(seed=seed, arm=arm, run_id=run_id)
        for role, (seed, arm, run_id) in RUNS.items()
    }
    effect_contrasts = contrasts(results=results)
    payload = {
        "runs": results,
        "contrasts": effect_contrasts,
        "gates": gates(results=results, effect_contrasts=effect_contrasts),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
