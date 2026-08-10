# EXP-010 — Population redundancy after enforcement

**Status:** completed — population changed coordination; enforcement recovery not exercised
**Date opened:** 2026-08-04
**Date closed:** 2026-08-04

## Question

Was the seed-44 covenant collapse primarily caused by the four-provider
population having only one spare worker, or does the institution still fail to
continue when six active members can absorb the same two-person sanction?

## Expected decision

- Add the two six-provider runs regardless of the independent result.
- Preserve team size three, economics, zones, audit exposure, attestation
  exposure, model, and seed across the paired conditions.
- Treat nine rounds as a population diagnostic, not a stability horizon.
- If a detected violation removes two members and the covenant continues with
  the remaining four, attribute the earlier immediate production halt partly to
  the small-population design.
- If the larger institution still stops producing, inspect coordination and
  membership behavior before changing sanction severity.
- Do not start the long-horizon experiment until permanent-expulsion semantics
  and the population diagnostic are validated.

## Design

Two fresh nine-round Sonnet runs at seed 44. Six persistent providers compete
for three-person teams. All six are initially active association members in the
covenant arm; all six are eligible in the independent arm. The covenant keeps
the current rule that both the faulty worker and accountable lead are fined and
permanently expelled after an audited incorrect delivery.

The audit and attestation schedules are explicitly frozen to the first nine
draws of the original four-provider seed-44 generator. This is necessary because
the prior generator consumed the same RNG for provider rotation and subsequent
audit draws, so changing population size would otherwise also change exposure
to enforcement. Zones and economic profiles remain seeded as before. Private
channel capacity rises from 24 to 36 only to preserve four slots per round.

Agents still know this diagnostic lasts nine rounds. A hidden or stochastic
horizon belongs to the subsequent stability experiment and is not introduced
here.

## Outcomes inspected

- effort, completion, correctness, and payment;
- occurrence and attribution of audited failures;
- refund source, sanctions, and expelled members;
- active membership and team staffing after enforcement;
- number of rounds until production resumes;
- comparison with the four-provider seed-44 pair from EXP-009.

## Provenance

- Commit: pending
- Independent config:
  `src/glossogen/scenarios/bonded_team_production/knobs_population_test_independent_seed44.json`
- Covenant config:
  `src/glossogen/scenarios/bonded_team_production/knobs_population_test_covenant_seed44.json`
- Independent run: `runs/bonded_team_production/1785868961`
- Covenant run: `runs/bonded_team_production/1785869805`
- API cost: $7.7577291

## Result

| Condition | Inspections | Completed | Correct completed | Promised / paid |
|---|---:|---:|---:|---:|
| Independent | 18/27 | 9/9 | 7/9 | 503 / 503 |
| Covenant | 17/27 | 8/9 | 6/8 | 470 / 420 |

All six covenant members remained active. No audited incorrect delivery
occurred within the resolvable audit window, so neither expulsion nor
post-expulsion staffing was observed. The covenant delivered incorrect orders
in rounds 8 and 9. Round 8 was not sampled for audit, while the round-9 audit
was scheduled to resolve in round 10, beyond the nine-round diagnostic.

Population size changed behavior before any enforcement occurred. In the first
six rounds, the six-provider independent market inspected 12/18 units and
completed all six orders, compared with 11/18 inspections and five completions
in the original four-provider seed-44 run. The six-provider covenant inspected
13/18 units and completed all six orders, compared with 5/18 inspections and
two completions in the original four-provider run. It then had one coordination
failure in round 7 despite two completed inspections, followed by two completed
but incorrect orders.

The paired six-provider arms showed very similar aggregate service performance.
The covenant did not improve effort, completion, or the absolute number of
correct deliveries in this trajectory. Its agents were consistently truthful
in the requested attestations, including explicit disclosure of uninspected
work, but those disclosures did not prevent later incorrect delivery.

## Outcome

**Inconclusive for enforcement recovery.** Six providers remove the earlier
mathematical impossibility: after a two-person sanction, four members would
remain and could still form a three-person team. However, this run never
activated the sanction, so it cannot show whether the agents actually resume
production after enforcement.

**Supported for population sensitivity.** Moving from four to six providers
substantially changed negotiation, effort, and completion even with the same
seeded cases and frozen audit exposure. The seed-44 collapse cannot be treated
as population-invariant evidence about covenant stability.

## Validity limitations

- One trajectory per condition cannot estimate a population-size treatment
  effect, especially because adding providers also changes the set of agents
  participating in negotiation and the lead rotation.
- Nine known rounds are sufficient for this diagnostic but not evidence of
  long-horizon stability or intergenerational transmission.
- The audit schedule did not resolve either incorrect covenant delivery. This
  prevented the experiment from reaching its main enforcement-recovery branch.
- The four-provider source run did not truly enforce its configured permanent
  re-entry prohibition. That implementation gap was fixed before EXP-010, but
  no expulsion occurred here to exercise the fix.

## What it changed

- Do not infer that simply adding rounds will answer the recovery question. A
  targeted audited-failure challenge is needed first; otherwise a longer run
  can again fail to activate enforcement.
- Keep six providers for the next enforcement diagnostic so loss of a worker
  and lead does not make staffing mathematically impossible.
- Separate a controlled enforcement-recovery test from the later stability
  experiment. The former needs guaranteed exposure to an audited failure; the
  latter needs a longer, hidden or stochastic horizon and multiple runs.
- Treat provider count as an experimental parameter, not merely additional
  redundancy, because it changes bargaining and coordination behavior.

## Traps found

- Changing `provider_count` changed later audit and attestation draws because
  the original generator reused one RNG stream for provider shuffling and case
  exposure. EXP-010 added explicit schedules so the intended exposure could be
  held fixed.
- An audit scheduled on the final round never resolves inside the run. Analysis
  must distinguish scheduled audits from resolved audits.
- More available providers do not guarantee completion: round 7 still failed
  after two inspections because the final submission/delivery sequence did not
  close.
- The prior `expulsion_permanent` knob was declarative only. The world now
  rejects re-entry attempts when it is enabled and tests cover both permanent
  and non-permanent behavior.
