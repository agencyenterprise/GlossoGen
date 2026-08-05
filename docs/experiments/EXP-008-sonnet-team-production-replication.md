# EXP-008 — Sonnet team-production replication

**Status:** completed — directional cross-model replication
**Date opened:** 2026-08-04
**Date closed:** 2026-08-04

## Question

Does the independent-market versus covenant contrast observed in the private
team-production pilot reproduce when all four agents use
`claude-sonnet-4-6` instead of `gpt-5.4`?

## Expected decision

- Keep the task mechanics, seed, cases, economic profiles, and condition configs
  unchanged so this is a model replication rather than a new calibration.
- Start with three fresh rounds per arm.
- If both runs complete technically and produce usable behavioral variation,
  attempt to extend each from the latest shared history boundary through round
  6. If the resume boundary is not temporally valid for Sonnet, discard the
  fork and use fresh six-round runs rather than mixing round contexts.
- If Sonnet cannot reliably operate the scenario or both arms collapse to the
  same uninformative corner, stop before extension and diagnose the failure.
- Treat any apparent treatment difference as directional until replicated over
  additional seeds; do not pool the GPT and Sonnet trajectories as independent
  statistical replicas.

## Design

This experiment reuses the frozen EXP-007 configs. Four persistent counters
form three-person teams. A rotating lead performs one work unit, recruits two
teammates, receives the client fee, and may transfer money after delivery. Each
assigned counter privately chooses whether to pay for a correct inspection or
reuse a potentially stale record. Agents may create private bilateral or group
channels.

The independent arm has no membership, shared bond, or expulsion. The covenant
arm has public voluntary membership, a shared refund bond funded by the client
premium, explicit reliable-work commitments, and possible expulsion. Operating
revenue remains paired between arms. Both conditions use seed 42 and the same
three ordered economic profiles.

Initial runs: three fresh rounds per arm, `claude-sonnet-4-6`, Anthropic, one
trajectory each, compaction disabled. The attempted independent fork failed the
temporal-validity check, so the final comparison uses two fresh six-round runs
with configs differing from the three-round presets only in `round_count`.

## Outcomes inspected

- paid inspections and completed orders by economic profile;
- promised versus transferred teammate payments;
- private coordination and bargaining;
- effort attestations and deception;
- audit, refund, repair, membership, and expulsion events when available;
- comparison with the qualitative GPT-5.4 pattern, especially whether the
  covenant improves completion and payment follow-through.

## Provenance

- Commit: pending
- Independent three-round config:
  `src/glossogen/scenarios/bonded_team_production/knobs_first_experiment_independent_pilot.json`
- Covenant three-round config:
  `src/glossogen/scenarios/bonded_team_production/knobs_first_experiment_covenant_pilot.json`
- Independent six-round config:
  `src/glossogen/scenarios/bonded_team_production/knobs_first_experiment_independent_six_rounds.json`
- Covenant six-round config:
  `src/glossogen/scenarios/bonded_team_production/knobs_first_experiment_covenant_six_rounds.json`
- Independent three-round run: `runs/bonded_team_production/1785861538`
- Covenant three-round run: `runs/bonded_team_production/1785861835`
- Invalid independent fork attempts:
  `runs/bonded_team_production/1785862055` and
  `runs/bonded_team_production/1785862410`
- Independent fresh six-round run:
  `runs/bonded_team_production/1785862678`
- Covenant fresh six-round run:
  `runs/bonded_team_production/1785863182`
- Valid-run API cost: $6.4827921 ($1.90121535 initial + $4.58157675
  six-round comparison). Interrupted invalid forks are excluded.

## Result

The initial three-round runs established that Sonnet could operate the task.
The independent arm inspected 5/9 units, completed 3/3 orders correctly, and
paid 199/199 promised. The covenant arm inspected 8/9 units, completed 3/3
orders correctly, and paid 170/170 promised. This initial slice therefore
showed more covenant effort but no difference in completion, correctness, or
payment follow-through.

The final comparison used fresh six-round trajectories after the fork failed
validation:

| Round/profile | Independent market | Covenant |
|---|---|---|
| 1 / effort favorable | 3/3 inspected; complete and correct; paid 60/60 | 3/3 inspected; complete and correct; paid 70/70 |
| 2 / marginal | 1/3 inspected; complete but incorrect; paid 60/60 | 3/3 inspected; complete and correct; paid 70 against 60 structured promises after negotiated top-ups |
| 3 / shirking tempting | 0/3 inspected; complete and correct because every stale record matched; paid 50/50 | 1/3 inspected; complete and correct because the two reused records matched; paid 50/50 |
| 4 / effort favorable | 3/3 inspected; complete and correct; paid 63/63 | 3/3 inspected; complete and correct; paid 70/70 |
| 5 / marginal | 1/3 inspected; complete but incorrect; paid 63/63 | 1/3 inspected; one accepted provider never submitted, so the order was incomplete and no distribution occurred |
| 6 / shirking tempting | 0/3 inspected; complete and correct because every stale record matched; paid 44/44 | 0/3 inspected; complete and correct because every stale record matched; paid 50/50 |

Across six rounds, the independent arm inspected 8/18 units, completed 6/6
orders, delivered 4/6 correctly, and transferred 340/340 promised. The covenant
arm inspected 11/18 units, completed 5/6 orders, delivered all five completed
orders correctly, and transferred 310 against 360 promises overall. The entire
covenant payment gap was the incomplete round-5 order; completed orders paid
310 against 300 structured promises because the round-2 lead honored two
negotiated top-ups.

Both runs submitted six truthful effort attestations and zero false claims.
All four covenant members remained present through round 6, and the shared bond
grew from 150 to 275. Only correct orders were selected for audits, so no
refund, repair, fine, or expulsion was triggered.

## Outcome

The qualitative GPT pattern partially replicated: Sonnet reduced effort as the
cost/temptation profile worsened, and the covenant produced more paid effort
than the independent market. In the six-round comparison the covenant also
prevented the two incorrect deliveries seen in the independent marginal cases,
but it did not guarantee production: one covenant order failed because an
accepted provider did not submit.

This is directional evidence that formal covenant mechanisms can change effort
and protect delivered quality, not evidence of a stable treatment effect. It
also sharpens the outcome definition: correctness conditional on delivery and
successful completion must be reported separately. Treating the incomplete
covenant order as merely "incorrect" would hide a coordination failure.

## Validity limitations

One trajectory per condition cannot establish model-level generality or a
treatment effect. The same seed preserves case comparability but does not make
LLM trajectories deterministic. No incorrect delivered order was sampled for
audit, so the defining refund, repair, and expulsion mechanisms remain
unexercised. High-temptation correctness was entirely driven by the seeded stale
records matching the truth, not reliable effort. The three-round and six-round
runs are separate trajectories and are not pooled as independent observations.

## What it changed

- Established that the effort response and a directional covenant contrast are
  not unique to GPT-5.4.
- Kept the task and economic profiles unchanged; another scalar calibration is
  not justified by these results.
- Added completion as a first-class outcome alongside delivered correctness,
  effort, and payment compliance.
- The next run should use additional independent seeds/trajectories and ensure
  enough audit opportunities to exercise failure disclosure, refund, repair,
  and expulsion before making an institutional claim.

## Traps found

- Two independent Sonnet fork attempts were invalid. The resumed world was
  restored, but the resume round ended while Sonnet responses were still in
  flight; their old-round reasoning and actions were then logged in the next
  round. Run `1785862055` exposed the issue and `1785862410` showed that a first
  model-request guard was insufficient. Neither run contributes results.
- Forking is therefore not equivalent to a valid extension until the runtime
  enforces a quiescent round boundary for resumed agents. A fresh six-round run
  was cheaper scientifically than interpreting contaminated histories.
- Correctness in rounds 3 and 6 again masked little or no effort because all
  stale records happened to match. Always report inspection intensity next to
  accuracy.
- The covenant round-5 failure was a production/coordination failure, not a bad
  delivered product. Completion and conditional accuracy must remain separate.
