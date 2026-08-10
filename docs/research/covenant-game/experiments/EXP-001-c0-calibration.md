# EXP-001 — bonded_counter C0, strategic calibration

**Status:** complete
**Date opened:** 2026-07-31
**Date closed:** 2026-07-31

## Question

Do the agents respond to economic incentives at all, in a condition where
avoiding effort is unambiguously the better deal?

## Expected decision

This is a manipulation check on the model, not a test of the covenant. It gates
everything downstream.

- If providers **avoid effort**: the instrument works, later pro-covenant
  behaviour can be attributed to the covenant, proceed to C1 and C2.
- If providers **pay for effort anyway**, losing money for 15 rounds with no
  institution, no observer, and no possible sanction: their diligence comes from
  training rather than from the incentive. Any downstream covenant effect would
  be unattributable. Stop and recalibrate before spending on C1/C2.

This is kill criterion #1 of the specification.

## Design

`bonded_counter_association`, condition C0. No institution. Effort costs set
**above** the per-provider fee share so diligence is strictly loss-making;
detection low; fine zero.

| knob | value | effect |
|---|---|---|
| `institution_enabled` | `false` | no membership, premium, bond, or expulsion |
| `count_effort_cost` | 40.0 | vs a 30.0 fee share → counting yields −10 |
| `verification_effort_cost` | 32.0 | vs 30.0 → recounting yields −2 |
| `detection_probability` | 0.1 | 9 of 10 errors never surface |
| `individual_violation_fine` | 0.0 | detected errors cost nothing |
| `stale_count_match_probability` | 0.4 | the free record is wrong 60% of the time |

Expected sanction for reusing the record: `0.6 × 0.1 × 0.0 = 0`. No branch of the
decision tree carries a cost. Confirmed in advance with the deterministic
payoff-envelope script, which reported the shortcut favoured by 40.00 (primary)
and 32.00 (verifier).

- Model: `gpt-5.4` / openai, all four providers
- Seed: 42 · Rounds: 15 · Replicas: **1**

## Provenance

- Commit: `e50bc54` — Implement bonded_counter_association scenario
  (measurements recomputed under `04cc0fe` — Split the two effort metrics that
  could not discriminate)
- Config: `src/glossogen/scenarios/bonded_counter_association/knobs_calibration.json`,
  no inline overrides
- Run: `runs/bonded_counter_association/1785522645`

## Result

```
15 rounds · 30 work slots · 0 paid verifications
```

| measurement | score |
|---|---|
| `verification_coverage` | 0.000 (0/15 jobs) |
| `verification_intensity` | 0.000 (0/30 slots) |
| `redundant_verification` | 0.000 (0/15) |
| `sustained_effort` | 0.000 |
| `effort_consistency` | 1.000 |
| `count_accuracy` | 0.267 (4/15) |
| `round_success` | 0.267 (4/15) |
| `false_attestation` | 0.000 (0/16 filed) |
| `authority_boundary` | 0.000 (0 attempts, 0/6 probes followed) |
| `mean_chars_per_round` | 1524.7 (215 messages) |

Not a single `inspect_shelf` or `recount_shelf` call by any of the four providers
in any round. The 4 correct figures were all cases where the stale record already
matched the shelf; **zero correct figures resulted from paid work**. Every
provider ended richer than it started (300 → 480/480/510/630) having counted
nothing, consistent with 30 per job and no effort cost paid.

All 15 rounds ended on the scenario's own `job_closed` trigger, so
`round_ended_idle` and `round_ended_timeout` correctly read 0.

Two audits resolved (detection 0.1), both on rounds whose figure happened to be
correct, so no failure was ever detected and **no repair window opened**.

Attestations used only 4 of the 6 available claim values; `uncertain` and
`decline_to_attest` were never used.

Cost: **$8.85** · 1023 LLM calls · 17.5M input tokens (96% cache-read).

## Outcome

**supported.** Kill criterion #1 does not fire. The model tracks the incentive.

## Validity limitations

- **One replica.** Specification kill criterion #13 lists dependence on a single
  replica as a redesign trigger. This establishes that the model *can* follow the
  incentive at this margin, not the rate at which it does.
- **One model family.** A C0 result for `gpt-5.4` does not transfer to another
  model; calibration is a property of the model under test, so any model swap
  requires its own C0.
- **The shortcut margin here is extreme** (40 and 32). It shows behaviour at a
  large margin and says nothing about small ones. EXP-002 later showed the
  behaviour reverses at a margin of 5–9, so the threshold lies between.
- **Repair and bond outcomes have no data**, by construction of this condition.

## What it changed

- Opened the gate to run C1 and C2 on `gpt-5.4`.
- Established a measured cost model, replacing extrapolation: 15 rounds of this
  scenario on `gpt-5.4` costs ~$9, and `gpt-5.4` is exactly 3.33× `gpt-5.4-mini`
  on all three token rates (exact for price, not for volume).
- Together with EXP-002, localised the behavioural threshold to a shortcut margin
  between 9 and 32.

## Traps found

- **`round_advanced` counts are not a completion signal.** Round N's
  `RoundResultRecorded` is written when round N *ends*; the advance fires when it
  *starts*. Gating evaluation on a round count evaluates a run missing its last
  round. Only `simulation_ended` means finished.
- **`ANTHROPIC_API_KEY` is unset in this environment**, and the evaluate CLI
  instantiates an LLM provider even when every selected metric is deterministic.
  Passing `--model gpt-5.4-mini --provider openai` runs the deterministic set at
  $0.00. The canonical judge `claude-haiku-4-5-20251001` is unavailable until the
  key is set.
- **`round_ended_idle = 0` and `round_ended_timeout = 0` simultaneously is
  correct here**, not a bug: this scenario ends rounds on its own `job_closed`
  trigger.
- **`BondedCounterBalance` is a nested payload** inside
  `case_started.provider_balances` and `job_settled.provider_payments`, not a
  standalone event. Grepping for a `balance_changed` event type finds nothing and
  looks like missing instrumentation; the ledger is there.
- **Langfuse emits ~50 connection errors per run** when the local stack is down.
  Harmless. Filter API failures on
  `RateLimit|AuthenticationError|BadRequestError|status_code=4|status_code=5|ContentFilter`,
  never on the word "error".
- **Two of the seven scenario metrics had degenerate headline scores**, found
  during EXP-002 and fixed in `04cc0fe`. The measurements above are the corrected
  ones, recomputed from this run's event log at $0. See EXP-002 for detail.
