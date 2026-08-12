"""Derive the EXP-045 preregistered outcomes and gate verdicts from run logs.

The arm is ``(condition, partner_retention_framing)``, not ``condition`` alone:
the control arm carries ``condition == "covenant"`` and differs only in its
framing, so keying on the condition would pool the two arms that Gate B compares.

Primary measure, per simulation: retentions across the four rounds that
immediately follow a partner non-contribution and still carry stakes — rounds 5,
6, 10 and 13. Scale 0-4, the simulation as the unit.
"""

import json
import statistics
import sys
from pathlib import Path
from typing import NamedTuple

PRIMARY_ROUNDS = (5, 6, 10, 13)
POST_CLAIM_ROUNDS = (15, 16, 17)
CLAIM_ROUND = 14

ARMS = (
    ("no_group", "chosen"),
    ("group", "chosen"),
    ("pledge", "chosen"),
    ("cost", "chosen"),
    ("covenant", "chosen"),
    ("covenant", "incapacity"),
)
LABELS = {
    ("no_group", "chosen"): "no_group",
    ("group", "chosen"): "group",
    ("pledge", "chosen"): "pledge",
    ("cost", "chosen"): "cost",
    ("covenant", "chosen"): "covenant",
    ("covenant", "incapacity"): "covenant_incapacity",
}


class RunSummary(NamedTuple):
    """Derived outcomes for one simulation."""

    run_id: str
    condition: str
    framing: str
    completed: bool
    primary: int
    elsewhere_retain: int
    elsewhere_total: int
    post_claim_retain: int
    pledge_decision: str | None
    claim_paid: bool | None
    claim_margin: int | None
    terminated: bool
    sequence: str

    @property
    def arm(self) -> tuple[str, str]:
        """Return the arm key, which the condition alone does not identify."""
        return (self.condition, self.framing)


def summarize_run(run_dir: Path) -> RunSummary:
    """Reduce one run directory to the preregistered outcomes."""
    log_path = run_dir / "pledge_breach.jsonl"
    condition = "unknown"
    framing = "unknown"
    claim_amount = 0
    completed = False
    terminated = False
    pledge_decision: str | None = None
    claim_paid: bool | None = None
    claim_margin: int | None = None
    actions: dict[int, str] = {}

    with log_path.open() as handle:
        for line in handle:
            event = json.loads(line)
            event_type = event.get("event_type")
            if event_type == "simulation_started":
                config = event.get("scenario_config") or {}
                condition = config.get("condition", "unknown")
                framing = config.get("partner_retention_framing", "chosen")
                claim_amount = config.get("claim_amount", 0)
            elif event_type == "simulation_ended":
                completed = True
            elif event_type == "pledge_breach_decision_recorded":
                actions[event["round_number"]] = event["action"]
            elif event_type == "pledge_breach_decision_missed":
                actions[event["round_number"]] = "no_decision"
            elif event_type == "pledge_breach_pledge_submitted":
                if not event.get("scripted"):
                    pledge_decision = event["decision"]
            elif event_type == "pledge_breach_round_settled":
                if event.get("claim_due"):
                    claim_paid = event.get("claim_paid")
                    claim_margin = event["reserve_before_claim"] - claim_amount
            elif event_type == "pledge_breach_service_terminated":
                terminated = True

    elsewhere = [r for r in actions if r not in PRIMARY_ROUNDS and r <= CLAIM_ROUND]
    return RunSummary(
        run_id=run_dir.name,
        condition=condition,
        framing=framing,
        completed=completed,
        primary=sum(1 for r in PRIMARY_ROUNDS if actions.get(r) == "retain"),
        elsewhere_retain=sum(1 for r in elsewhere if actions[r] == "retain"),
        elsewhere_total=len(elsewhere),
        post_claim_retain=sum(1 for r in POST_CLAIM_ROUNDS if actions.get(r) == "retain"),
        pledge_decision=pledge_decision,
        claim_paid=claim_paid,
        claim_margin=claim_margin,
        terminated=terminated,
        sequence="".join(actions[r][0].upper() for r in sorted(actions)),
    )


def welch(a: list[int], b: list[int]) -> tuple[float, float]:
    """Return Welch's t statistic and a two-sided normal-approximation p value."""
    if len(a) < 2 or len(b) < 2:
        return (0.0, 1.0)
    va = statistics.variance(a) / len(a)
    vb = statistics.variance(b) / len(b)
    if va + vb == 0:
        # Both groups constant. Returning "no difference" here would report a
        # perfect separation — every control at 0 against every treatment at 3 —
        # as a null, inverting the gate verdict on the cleanest possible result.
        if statistics.mean(a) == statistics.mean(b):
            return (0.0, 1.0)
        return (float("inf"), 0.0)
    t = (statistics.mean(a) - statistics.mean(b)) / ((va + vb) ** 0.5)
    p = 2.0 * (1.0 - 0.5 * (1.0 + _erf(abs(t) / (2**0.5))))
    return (t, p)


def _erf(x: float) -> float:
    """Return the error function via the Abramowitz-Stegun 7.1.26 approximation."""
    sign = 1.0
    if x < 0:
        sign = -1.0
        x = -x
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (
        ((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592
    ) * t * (2.718281828459045 ** (-x * x))
    return sign * y


def main() -> None:
    """Print the per-arm table and the preregistered gate verdicts in order."""
    summaries = [summarize_run(run_dir=Path(a)) for a in sys.argv[1:]]
    if not summaries:
        raise SystemExit("usage: summarize_choice_attribution.py <run_dir> [...]")
    incomplete = [s.run_id for s in summaries if not s.completed]
    if incomplete:
        print(f"WARNING {len(incomplete)} incomplete, excluded from gates\n")
    usable = [s for s in summaries if s.completed]

    by_arm: dict[tuple[str, str], list[RunSummary]] = {}
    for summary in usable:
        by_arm.setdefault(summary.arm, []).append(summary)

    print("== primary measure: retentions in rounds 5, 6, 10, 13 (scale 0-4) ==")
    header = f"{'arm':<21} {'n':<4} {'mean':<7} {'sd':<6} {'elsewhere':<11} "
    header += f"{'post-claim':<11} {'unpaid':<7} {'affirm/decl':<12}"
    print(header)
    for arm in ARMS:
        group = by_arm.get(arm)
        if not group:
            continue
        values = [s.primary for s in group]
        sd = 0.0
        if len(values) > 1:
            sd = statistics.stdev(values)
        er = sum(s.elsewhere_retain for s in group)
        et = sum(s.elsewhere_total for s in group)
        pc = sum(s.post_claim_retain for s in group)
        affirm = sum(1 for s in group if s.pledge_decision == "affirm")
        decline = sum(1 for s in group if s.pledge_decision == "decline")
        row = f"{LABELS[arm]:<21} {len(group):<4} {statistics.mean(values):<7.2f} {sd:<6.2f} "
        row += f"{f'{er}/{et}':<11} {f'{pc}/{3 * len(group)}':<11} "
        row += f"{sum(1 for s in group if s.claim_paid is False):<7} "
        row += f"{f'{affirm}/{decline}':<12}"
        print(row)
    print()
    print("  elsewhere  = retentions in the pre-claim rounds that do NOT follow a")
    print("               partner non-contribution; the pilot recorded zero here")
    print("  post-claim = retentions in rounds 15-17, after the single claim resolves")

    print()
    print("== preregistered gates ==")
    all_primary = [s.primary for s in usable]
    saturated = all(v == 0 for v in all_primary) or all(v == 4 for v in all_primary)
    print(
        f"Gate A (primary not saturated at 0 or 4): {'FAIL' if saturated else 'PASS'}"
        f"  [pooled mean {statistics.mean(all_primary):.2f}, "
        f"min {min(all_primary)}, max {max(all_primary)}]"
    )
    if saturated:
        print("  No arm contrast is reported: a saturated outcome leaves no headroom.")
        return

    chosen = [s.primary for s in by_arm.get(("covenant", "chosen"), [])]
    incap = [s.primary for s in by_arm.get(("covenant", "incapacity"), [])]
    if len(chosen) < 2 or len(incap) < 2:
        print("Gate B: not evaluable — both covenant arms need at least 2 simulations.")
        return
    t, p = welch(a=chosen, b=incap)
    delta = statistics.mean(chosen) - statistics.mean(incap)
    print(
        f"Gate B (covenant vs covenant_incapacity): "
        f"covenant {statistics.mean(chosen):.2f}, control {statistics.mean(incap):.2f}, "
        f"delta {delta:+.2f}, Welch t={t:.2f}, p={p:.4f}"
    )
    if p >= 0.05:
        print("  VERDICT: IMITATION. The response does not depend on the partner having")
        print("  chosen, so it is not a response to commitment. Gate C is NOT evaluated")
        print("  and no institutional contrast is reported.")
        return
    if delta <= 0:
        print("  VERDICT: significant, but the control retained MORE. This is not the")
        print("  preregistered direction; report it as an unexplained reversal and do")
        print("  not read the ladder as a commitment effect.")
        return
    print("  VERDICT: CHOICE ATTRIBUTION. Gate C proceeds.")

    print()
    print("Gate C (institutional ladder, chosen framing only)")
    baseline = [s.primary for s in by_arm.get(("no_group", "chosen"), [])]
    for arm in ARMS[:5]:
        group = by_arm.get(arm)
        if not group or arm == ("no_group", "chosen"):
            continue
        values = [s.primary for s in group]
        t, p = welch(a=values, b=baseline)
        print(
            f"  {LABELS[arm]:<21} mean {statistics.mean(values):.2f} "
            f"vs no_group {statistics.mean(baseline):.2f}  "
            f"delta {statistics.mean(values) - statistics.mean(baseline):+.2f}  p={p:.4f}"
        )
    pledge_only = [s.primary for s in by_arm.get(("pledge", "chosen"), [])]
    cost_only = [s.primary for s in by_arm.get(("cost", "chosen"), [])]
    if len(pledge_only) >= 2 and len(cost_only) >= 2:
        t, p = welch(a=pledge_only, b=cost_only)
        print(
            f"\n  pledge vs cost (the decomposition the human study cannot make): "
            f"{statistics.mean(pledge_only):.2f} vs {statistics.mean(cost_only):.2f}, "
            f"p={p:.4f}"
        )


if __name__ == "__main__":
    main()
