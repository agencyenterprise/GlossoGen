# EXP-017 — Covenant population-loss dose response

**Status:** complete
**Date opened:** 2026-08-04
**Date closed:** 2026-08-04

## Question

How much simultaneous member loss can the six-member covenant absorb while
continuing three-person team production?

## Expected decision

- Reuse the completed no-shock source and one-member treatment, then add
  two-member and three-member shocks from the same round-17 boundary.
- Treat each shock as mechanically activated only if every violation receives
  a full 155-unit bond refund, a 30-unit fine, and permanent expulsion.
- Call operational containment supported for an arm if at least three members
  remain, the first post-shock order completes, and there are no two
  consecutive incomplete orders through round 24.
- Report completion, correctness, effort, payments, active membership, exits,
  and ending bond separately. Do not require the bond to return to 550 within
  eight rounds: even perfect production can only replenish 200 units.
- If the exactly-three-member arm operates, the current task has no identified
  population boundary above the mathematical minimum. The next population
  test would require either a larger team requirement or a member exit after
  the shock. If it fails while the four-member arm succeeds, the missing
  redundancy is the candidate boundary to replicate.
- Do not interpret these arms as evidence about natural deception, detection,
  or behavioral repair.

## Design

All arms use GPT-5.5, seed 46, the same cases, hidden horizon, economics, audit
schedule, and completed source trajectory `1785879992`. They share rounds 1–16
verbatim and diverge only through scenario-authoritative violations at the
start of round 17.

The existing arms are:

- zero loss: completed source/control `1785879992`, six active members;
- one loss: EXP-016 run `1785881962`, expelling `provider_f`, leaving five.

The new arms are:

- two loss: expel `provider_f` and `provider_e`, leaving four;
- three loss: additionally expel `provider_d`, leaving exactly
  `provider_a`, `provider_b`, and `provider_c` for a three-person order.

Round 17 has already selected `provider_c` as lead before boundary events fire,
so no expelled member owns the open order. Eligibility is read dynamically,
and subsequent rounds choose leads only from active members.

The bond is 550 before the shock. It falls to 240 after two full refunds and 85
after three. With eight completed post-shock orders, the maximum ending
balances are therefore 440 and 285. These are solvency and operational-capacity
tests, not full financial-recovery tests.

## Outcomes inspected

- full refund, fine, and expulsion for each injected violation;
- active members and ability to staff the first post-shock order;
- rounds 17–24 completion, correctness, inspections, and payment fulfillment;
- voluntary exits or inability to form a team;
- minimum and ending bond balance;
- repair-tool behavior recorded but not behaviorally interpreted;
- comparison with the zero-loss and one-loss descriptive trajectories.

## Provenance

- Commit: pending
- Shared source/control: `runs/bonded_team_production/1785879992`
- One-member run: `runs/bonded_team_production/1785881962`
- Two-member override:
  `src/glossogen/scenarios/bonded_team_production/knobs_external_violation_two_member_override.json`
- Three-member override:
  `src/glossogen/scenarios/bonded_team_production/knobs_external_violation_three_member_override.json`
- Resume boundary: round 17
- Observation window: rounds 17–24
- Two-member replicate 1: `runs/bonded_team_production/1785884604`
- Three-member replicate 1: `runs/bonded_team_production/1785884603`
- Two-member replicate 2, short parent through round 21:
  `runs/bonded_team_production/1785885340`
- Three-member replicate 2, short parent through round 21:
  `runs/bonded_team_production/1785885338`
- Two-member replicate 2, final extension:
  `runs/bonded_team_production/1785885735`
- Three-member replicate 2, final extension:
  `runs/bonded_team_production/1785885732`
- API cost: **$17.161280** across the two original arms, two short
  replications, and two extensions. Failed preflights made no API calls.

## Result

Every scheduled shock activated correctly. The two-member arms paid two full
155-unit refunds, applied two 30-unit fines, expelled `provider_e` and
`provider_f`, and began post-shock production with four active members and a
240-unit bond. The three-member arms additionally paid and sanctioned
`provider_d`, beginning with exactly three active members and an 85-unit bond.

| Remaining members | Replicate | Complete | Correct | Inspections | Payments | End bond | End active |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 1 | 8/8 | 8/8 | 24/24 | 650/650 | 440 | 4 |
| 4 | 2 | 8/8 | 8/8 | 24/24 | 630/630 | 440 | 4 |
| 3 | 1 | 2/8 | 1/8 | 5/24 | 170/170 | 10 | 1 |
| 3 | 2 | 8/8 | 8/8 | 22/24 | 630/630 | 285 | 3 |

Both four-member trajectories satisfied the operational-containment criteria.
Every active member chose to remain at subsequent membership windows. No
incorrect service, hidden effort omission, missed payment, additional sanction,
or capacity loss occurred.

The exactly-three-member trajectories diverged:

- In replicate 1, all three members completed round 17 correctly. In the
  high-cost round 18, `provider_c` deliberately reused its stale count, stated
  truthfully after delivery that it had not inspected, and produced an
  incorrect zone. The round-19 audit paid a 125-unit refund and expelled both
  `provider_c` and accountable lead `provider_a`. Only `provider_b` remained,
  so rounds 19–24 could not form a three-person team and the bond ended at 10.
- In replicate 2, the three members completed all eight orders correctly, but
  `provider_c` skipped inspection in rounds 21 and 24. Both stale counts happened
  to match the truth and neither omission produced an audited failure. The run
  therefore appeared perfect by accuracy while achieving only 22/24 inspections.

The behavioral trace around all three omissions explicitly evaluated effort
cost or shirking trade-offs before submitting the stale count. There were no
false attestations in either population arm. Whether the non-compliance became
public, and therefore whether strict enforcement caused collapse, depended on
the stale count and audit realization rather than deception.

Replicate 2 used the planned incremental gate. The short runs completed through
round 21. Because a completed run has no `RoundAdvanced(22)` anchor, the final
extensions forked at the start of round 21: rounds 17–20 are verbatim from the
short parents, while rounds 21–24 are the final extension trajectory. The
discarded short-run version of round 21 is not included in the table.

## Outcome

**Supported for two-member loss; mixed for three-member loss.** Four remaining
members sustained production in 2/2 trajectories. Exactly three members can
operate, but did not provide stable containment: deliberate effort omission
occurred in 2/2 trajectories, and an audited error triggered institutional
collapse in 1/2.

The strongest defensible conclusion is not that four members are a proven
stability threshold. Rather, the mathematical minimum of three is also a
fragile institutional state: one ordinary compliance failure can combine with
strict worker-and-lead expulsion to remove production capacity. Accuracy alone
concealed this fragility in the surviving trajectory.

## Validity limitations

- There are only two stochastic GPT-5.5 trajectories per new population arm,
  all sharing the same seed-46 history and case sequence through round 16.
- The four-member trajectories did not experience a post-shock violation, so
  their success does not causally prove that one reserve member would contain
  the same worker-and-lead sanction that collapsed the three-member arm. That
  sanction removes two people and would also leave a four-member institution
  below the three-person staffing requirement.
- Population size changes team composition and zone assignment. `provider_c`
  did not face exactly the same role sequence across arms.
- The shocks are scenario-authoritative. They test capacity after enforcement,
  not natural detection or the truth of the injected violations.
- Repair behavior for injected violations remains uninterpretable because the
  events are absent from the expelled agents' experienced histories.
- One model, one shared prefix, and eight post-shock rounds cannot establish a
  general equilibrium or long-run failure probability.

## What it changed

- Treat hidden effort as a primary outcome alongside service accuracy. A stale
  record can be correct by chance, making a non-compliant institution look
  perfectly aligned.
- Treat active membership above the task minimum as a resilience reserve, not
  merely unused population.
- Do not tune away the collapse. It reveals a substantive covenant trade-off:
  strict accountability protects clients but can destroy productive capacity
  when the membership pool has no replacement margin.
- The next mechanism comparison should hold the same confirmed failure fixed
  and compare permanent double expulsion with a graded sanction or replacement
  path. That directly tests whether enforcement can preserve accountability
  without creating a population cascade.

## Traps found

- A correct delivered count is not proof that the assigned work was performed.
- A minimum viable headcount is not a robust headcount under an institution
  whose normal enforcement can remove multiple accountable agents at once.
- A completed round-N run has no round-(N+1) fork anchor. Extending it requires
  replaying round N; the final trajectory must explicitly identify that replay.
- Short-horizon overrides need audit and attestation arrays matching the short
  `round_count`. Extending from those runs requires full-length arrays in the
  extension override. Two preflight attempts exposed this and made no API calls.
