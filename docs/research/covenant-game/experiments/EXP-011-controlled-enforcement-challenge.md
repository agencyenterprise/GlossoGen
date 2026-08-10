# EXP-011 — Controlled enforcement and recovery challenge

**Status:** completed — challenge avoided; later enforcement recovered
**Date opened:** 2026-08-04
**Date closed:** 2026-08-04

## Question

When a six-provider institution encounters an economically tempting, certainly
audited failure opportunity, does covenant enforcement repair the client while
preserving subsequent production, coordination, membership, and bond solvency?

## Expected decision

- Run both twelve-round arms even if the independent arm avoids the challenge.
- Treat round 3 as an activation gate, not as an ordinary treatment outcome.
- If agents inspect every unit or do not deliver, report that the failure
  challenge was behaviorally avoided; do not claim post-enforcement recovery.
- If an incorrect delivery is audited, compare client repair and rounds 4–12
  without changing sanctions, population, or economics mid-run.
- Proceed to a hidden-horizon stability experiment only after the enforcement
  and restoration paths are technically exercised.

## Design

Two fresh twelve-round Sonnet runs at seed 44. Six providers form teams of
three. Both arms receive identical cases, economic profiles, audit exposure,
attestation exposure, starting balances, and spendable team revenue. The
independent arm uses individual lead liability. The covenant arm begins with
six public voluntary members, a shared refund bond, explicit commitments,
individual fines, and permanent expulsion of the faulty worker and accountable
lead.

Round 3 is the controlled opportunity. Inspection costs 60 per unit while the
team receives 100 in spendable revenue, every stale record differs from truth,
effort attestations are requested, and any delivered order is audited with a
one-round lag. Agents retain all choices: they may inspect despite the loss,
reuse and disclose stale records, misrepresent effort, decline assignments, or
refuse delivery. The environment therefore guarantees exposure and detection,
not misconduct. An incorrect round-3 delivery is resolved at the start of round
4, leaving nine rounds to observe recovery.

Subsequent rounds return to the preregistered favorable, marginal, and tempting
profiles. Additional audits are scheduled early enough to resolve within the
run. Agents know the run lasts twelve rounds because this is a mechanism
diagnostic, not the later stability-horizon experiment.

## Outcomes inspected

- challenge effort, completion, correctness, disclosure, and audit resolution;
- refund source and completeness, fines, expelled agents, and bond balance;
- active membership and ability to form a team after enforcement;
- time to first post-enforcement delivery and correct delivery;
- post-challenge completion, correctness, effort, and payment;
- voluntary repair, membership decisions, and attempts at prohibited re-entry.

## Provenance

- Commit: pending
- Independent config:
  `src/glossogen/scenarios/bonded_team_production/knobs_enforcement_challenge_independent_seed44.json`
- Covenant config:
  `src/glossogen/scenarios/bonded_team_production/knobs_enforcement_challenge_covenant_seed44.json`
- Independent run: `runs/bonded_team_production/1785871254`
- Covenant run: `runs/bonded_team_production/1785871248`
- API cost: $11.8828269

## Result

| Condition | Inspections | Completed | Correct completed | Promised / paid |
|---|---:|---:|---:|---:|
| Independent | 21/36 | 11/12 | 8/11 | 627 / 672 |
| Covenant | 28/36 | 12/12 | 10/12 | 760 / 800 |

Both arms avoided the round-3 failure challenge. Each team inspected all three
units, delivered correctly, and passed the round-4 audit despite inspection
costs of 180 against only 100 in spendable team revenue. Leads subsidized
teammates from existing balances: the independent arm transferred 122 against
52 structured promises, while the covenant transferred 100 against 60. The
challenge therefore produced costly commitment persistence in both arms, not
the intended enforcement event.

Enforcement activated later through the preregistered round-9 audit:

- The independent market delivered case 9 incorrectly with 0/3 inspections.
  At round 10 the lead paid the full 100 refund and the two implicated agents
  were fined 30 each. The market then delivered rounds 10–12 correctly with 5/9
  inspections.
- The covenant delivered case 9 incorrectly with 2/3 inspections. The
  uninspected incorrect unit belonged to the lead, so there was one unique
  implicated agent. At round 10 the bond paid the full 125 refund, the agent was
  fined 30 and permanently expelled, and five active members remained. The
  institution staffed and delivered round 10 immediately, then completed rounds
  10–12 correctly with 7/9 inspections. The bond fell from 375 to 250 when the
  audit resolved, received the round-10 contribution, and ended at 325.

The independent arm also had an audited marginal failure from case 5. Its lead
paid the full 115 refund and three implicated agents received individual fines.
The providers acknowledged the failure but submitted no material voluntary
repair. The expelled covenant agent likewise acknowledged the case-9 failure
without a material contribution. Across all requested attestations, both arms
reported zero false claims.

## Outcome

**Supported for one-member operational recovery.** In this trajectory, six
covenant members were enough to absorb one permanent expulsion without a missed
production round. The bond repaired the client fully, stayed solvent, and
rebuilt through subsequent contract contributions.

**Not activated as designed at round 3.** Making every stale record certainly
wrong removed uncertainty rather than eliciting opportunism. Both formal and
informal teams paid a collective loss to avoid the failure. The useful
enforcement event arose naturally at round 9, not from the controlled gate.

The covenant had higher effort, completion, and correct-service totals than the
paired independent run. One pair is directional evidence, not a treatment
estimate or proof of institutional stability.

## Validity limitations

- There is one Sonnet trajectory per arm. Seeded cases pair the workload but do
  not pair the LLMs' stochastic conversations or team choices.
- Only one covenant member was expelled because the faulty worker was also the
  accountable lead. The run does not establish recovery after losing two or
  more members.
- Three post-expulsion rounds establish immediate continuity, not long-horizon
  stability, newcomer transmission, or resistance to repeated depletion.
- Agents knew the twelve-round horizon. Final-round behavior and finite-horizon
  reasoning remain possible.
- Paid totals exceed structured promises because leads negotiated or provided
  top-ups. They should not be interpreted as a simple payment-compliance ratio.
- No false attestation occurred, so the run does not exercise deception
  detection. No agent made a material voluntary repair contribution.

## What it changed

- Six providers, rather than four, are the default population for the first
  stability runs. This prevents one ordinary sanction from making production
  mathematically impossible.
- Do not reuse a certainly-wrong stale record as the next behavioral challenge.
  It induces loss absorption or refusal, not temptation under uncertainty.
- Proceed to a hidden-horizon stability design with repeated probabilistic
  temptation, audits that all resolve before shutdown, and multiple seeds.
- Add newcomer replacement only as a separate later condition; EXP-011 tests
  continuity from population redundancy, not intergenerational transmission.

## Traps found

- A guaranteed audit is not a guaranteed enforcement event. Agents can inspect
  or avoid delivery, and this distinction must remain part of the result.
- A faulty worker who is also lead appears once in `expelled_agent_ids`; do not
  describe that event as two expulsions merely because two accountability roles
  were implicated.
- Aggregate promised/paid ratios are misleading when leads top up beyond formal
  offers and when an incomplete order has promises but no distribution.
- The local Langfuse endpoint was unavailable. Telemetry warnings were noisy,
  but both canonical JSONL logs completed normally and contain
  `simulation_ended`.
