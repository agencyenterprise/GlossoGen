# EXP-012 — Hidden-horizon stability pilot

**Status:** complete
**Date opened:** 2026-08-04
**Date closed:** 2026-08-04

## Question

Over a repeated sequence without an announced final round, does the six-member
covenant produce more reliable effort, service continuity, truthful reporting,
repair, and institutional solvency than the paired independent market?

## Expected decision

- Run both fresh fifteen-round arms regardless of the first arm's outcome.
- Treat fifteen rounds as an incremental checkpoint, not proof of stability.
- Extend only if both runs complete technically and preserve behavioral
  variation rather than collapsing into universal inspection or universal
  shirking.
- Do not claim intergenerational transmission because this pilot has no
  newcomer replacement.
- If enforcement depletes membership below team size, stop that trajectory and
  report institutional failure rather than silently replenishing it.

## Design

Two fresh `gpt-5.5` runs through OpenAI at seed 45, with six providers and
three-person teams.
The arms receive identical cases, economic profiles, audit and attestation
schedules, starting balances, and spendable operating revenue. Economic
profiles cycle through effort-favorable, marginal, and shirking-tempting work.

The independent arm has individual lead liability and fines but no formal
membership, bond, or expulsion. The covenant arm begins with six public
voluntary members, a shared refund bond funded by the client premium, explicit
reliable-work commitments, individual fines, and permanent expulsion after an
audited violation.

The simulation executes fifteen rounds, but the system prompt describes an
ongoing sequence and does not disclose the final round. Seven paired audits are
scheduled on even-numbered cases and resolve one round later; none is left
pending at shutdown. Effort attestations are requested from rounds 2 through
14. Private channels and voluntary transfers remain available.

## Outcomes inspected

- inspection, completion, correct delivered service, and payment by profile;
- truthful and false effort attestations;
- audits, refunds, fines, expulsions, acknowledgements, and material repair;
- active membership, production continuity, and recovery after enforcement;
- bond minimum, ending balance, and ability to satisfy every refund;
- evidence of end-game behavior despite the hidden horizon.

## Provenance

- Commit: pending
- Independent config:
  `src/glossogen/scenarios/bonded_team_production/knobs_stability_pilot_independent_seed45.json`
- Covenant config:
  `src/glossogen/scenarios/bonded_team_production/knobs_stability_pilot_covenant_seed45.json`
- Independent run: `runs/bonded_team_production/1785873597`
- Covenant run: `runs/bonded_team_production/1785877472`
- API cost: $11.148382 ($5.730644 independent + $5.417738 covenant)

## Result

Both paired arms completed:

| Arm | Inspections | Completed | Correct completed | Promised / paid | Final bond |
|---|---:|---:|---:|---:|---:|
| Independent | 33/45 | 14/15 | 13/14 | 1062 / 982 | 150 |
| Covenant | 45/45 | 15/15 | 15/15 | 1310 / 1310 | 525 |

In the independent arm, all completed orders paid their structured promises in
full. The 80-unit gap comes entirely from round 13: all three providers
inspected and submitted, but the lead never delivered, so no distribution
occurred before the 300-second round timeout. The covenant completed and paid
the corresponding case.

The covenant inspected all three zones in every economic profile, including all
five shirking-tempting cases. The independent arm inspected only 3/15 zones in
the tempting profile: it shirked completely in rounds 3, 6, 9, and 15, then
temporarily inspected 3/3 in round 12. This produced the pair's only incorrect
delivery in independent round 3. Three other zero-effort deliveries happened to
be correct because all stale records matched the truth.

The independent agents submitted 36 truthful attestations and zero false
claims. They created only one private channel and sent two channel messages,
relying almost entirely on structured offers, submissions, and transfers.

The covenant submitted 39 truthful attestations and zero false claims, paid
every promise, and retained all six active members. Every provider ended with a
positive balance; their combined balance rose from 1800 to 1950. The bond
received all fifteen 25-unit contributions, rose from 150 to 525, and had no
pending liability at shutdown. The independent providers ended with a combined
balance of 2360. Their 410-unit advantage over covenant providers reflects
lower effort expenditure, not better service: the covenant spent 1575 on
inspection versus 1035 independently.

All seven audits in each arm resolved before shutdown and found correct orders.
Consequently, neither arm exercised refund, fine, expulsion, acknowledgement,
or material repair. The covenant's solvency result therefore means it funded
its bond while delivering correct work; it does not show that the bond could
survive a sequence of claims.

The hidden horizon worked operationally. Agents were never told that round 15
was final. The independent arm returned to 0/3 inspection in the final tempting
case, while the covenant preserved 3/3 effort; neither pattern suggests a
distinct announced-last-round effect. The pair cost $11.148382.

## Outcome

**Directional support, with an efficiency trade-off.** On the same cases and
economic schedule, the covenant shifted behavior from temptation-sensitive
effort to universal effort, prevented the independent arm's quality failure,
and avoided its coordination failure. It also preserved membership, provider
solvency, full payments, and a growing bond across this trajectory.

This is not yet evidence that every covenant mechanism contributed. The
treatment bundle produced reliable service, but at 540 more units of effort
cost and 410 less aggregate provider wealth than the independent arm. Because
it also reached a 45/45 effort ceiling and no audited failure occurred, this
pair primarily identifies a compliance-and-continuity contrast. It does not
identify the effects of the bond, repair, or expulsion separately.

## Validity limitations

- This is one paired GPT-5.5 trajectory at one seed, not a stability estimate.
- The covenant reached an effort and accuracy ceiling, so persistence beyond
  fifteen rounds may be observable but additional quality improvement is not.
- Correctness in three zero-effort tempting cases came from case luck, not
  reliable work.
- No audited failure occurred, leaving refund, enforcement, and repair behavior
  unexercised.
- No opportunistic entrant or newcomer replacement occurred, so resistance to
  invasion and transmission remain untested.
- Provider balances remained positive, but the treatment's collective economic
  margin was much smaller; a harsher workload could alter solvency.

## What it changed

- Keep both runs as the canonical seed-45 GPT-5.5 pair.
- Continue reporting completion separately from effort and correctness: round
  13 would disappear from an accuracy-among-deliveries metric.
- Do not interpret more rounds of the unchanged treatment as a test of repair or
  enforcement. Those mechanisms require a separate, pre-specified challenge.
- Use replication to test whether the compliance contrast recurs, then use
  targeted shocks or entrants to study durability and recovery.

## Traps found

- Parallel process creation is not atomic. The independent command started
  before the covenant command was rejected, leaving a scientifically valid but
  unpaired trajectory.
- The covenant arm was later authorized and launched separately from the frozen
  config; paired cases come from the shared seed and schedules, not simultaneous
  wall-clock execution.
- The model registry needed GPT-5.5 pricing before launch; otherwise the run
  would have been callable but its API cost would not have been tracked.
- A task can be fully inspected and submitted yet remain incomplete when the
  lead omits `deliver_order`.
