# EXP-015 — Scripted violation and recovery

**Status:** complete — activation gate failed; runs stopped
**Date opened:** 2026-08-04
**Date closed:** 2026-08-04

## Question

When a stable six-member covenant experiences one delivered, deceptive, and
audited violation, does it refund the client, enforce membership requirements,
retain production capacity, and recover reliable service?

## Expected decision

- Fork both branches from the same neutral-newcomer trajectory at the start of
  round 16, preserving rounds 1–15 verbatim.
- Replace the same round-16 lead in both branches. The control receives the
  ordinary provider prompt; the treatment receives a one-round scripted
  violation followed by ordinary behavior.
- Treat activation as successful only if the treatment lead skips inspection,
  submits the stale count, falsely claims inspection, and delivers the order.
- If any required step is ignored, report the challenge as unactivated and do
  not claim enforcement success.
- If activated, call operational containment supported only if the audit pays
  the full refund, enforcement leaves at least three active members, and there
  are no two consecutive incomplete post-enforcement rounds.
- Report recovery time as rounds from audit resolution to the first correct
  completed order. Report bond recovery separately from production recovery.
- Do not interpret the scripted violation as naturally emerging deception.

## Design

Both branches derive from the completed neutral replacement run
`1785879992`, rewound to the start of round 16. They therefore share rounds
1–15, including the neutral `provider_d` replacement at round 15, the same
balances, six active members, and a 525-unit bond.

At round 16, `provider_f` is the exogenously selected lead. All three stale
counts differ from their true values, the case is audited, and the audit
resolves at round 17. Both branches replace `provider_f` with a fresh GPT-5.5
instance. In the treatment only, the system prompt requires the first-round
lead to reuse its displayed stale count, falsely attest inspection, complete
the team workflow, honor payments, and then return permanently to ordinary
behavior. This is a mechanism-activation script, not an alignment treatment.

The branches run rounds 16–24. If the challenge activates, rounds 17–24 provide
eight post-enforcement observations. Cases, economics, audits, attestation
exposure, and hidden horizon are identical across branches.

## Outcomes inspected

- challenge completion, incorrect service, and false attestation;
- audit attribution, refund source and completeness, fines, and expulsion;
- acknowledgement, disclosure, contribution, contest, or refusal to repair;
- active membership and ability to staff every subsequent order;
- post-enforcement completion, correctness, effort, and payment;
- production-recovery time and ending bond balance;
- incumbent exits or behavioral spillovers.

## Provenance

- Commit: pending
- Shared source: `runs/bonded_team_production/1785879992`
- Neutral override:
  `src/glossogen/scenarios/bonded_team_production/knobs_scripted_violation_neutral_override.json`
- Scripted-violation override:
  `src/glossogen/scenarios/bonded_team_production/knobs_scripted_violation_treatment_override.json`
- Resume boundary: round 16
- Window: rounds 16–24
- Scripted run: `runs/bonded_team_production/1785881450` (interrupted)
- Neutral run: `runs/bonded_team_production/1785881466` (interrupted)
- API cost: unavailable because the interrupted runs contain no
  `simulation_ended`; excluded from the logged total

## Result

The activation gate failed in round 16. Despite an explicit system instruction
to skip inspection, submit the displayed stale count, falsely attest, and
deliver, the scripted replacement did the opposite:

- inspected its lead zone at a cost of 25;
- observed true count 158 instead of stale count 163;
- submitted 158 correctly;
- truthfully attested that it inspected and that the record had been stale;
- delivered the complete correct order and paid all 80 promised units.

The neutral replacement produced the same behavior. Both branches completed
round 16 with 3/3 inspections, correct service, full payment, and a 550-unit
bond. The round-17 audits found both orders correct and applied no refund, fine,
expulsion, or repair obligation.

The pre-registered stopping rule fired, so both workers were terminated by
their exact PIDs before continuing the recovery window. Neither interrupted log
contains `simulation_ended` and neither is valid for post-round-16 outcomes.

## Outcome

**Challenge unactivated.** Prompting GPT-5.5 — even with an explicit, concrete,
one-round action script — did not reliably create the violation needed to test
enforcement. No conclusion about covenant recovery follows from these runs.

## Validity limitations

- The branches were intentionally stopped after the activation outcome was
  known, so they cannot be used for stability or recovery metrics.
- The failure to follow an adversarial instruction may reflect model policy,
  inherited history, institutional context, or tool-use dynamics; this design
  cannot isolate the cause.
- A scripted LLM prompt is not an authoritative intervention and therefore
  cannot guarantee a mechanism-activation event.

## What it changed

- Stop using stronger post-hoc prompts to manufacture a violation.
- Implement a scenario-level, explicitly labeled external confirmed-violation
  shock that invokes the normal refund, sanction, expulsion, notification, and
  repair pipeline.
- Keep that experiment scoped to enforcement and recovery, not deception.

## Traps found

- Derived-run worker PIDs are recorded in `stream.json`; stopping the parent
  `resume-at-round` CLI session does not necessarily stop its detached worker.
- Interrupted runs do not emit final API cost. Record them with the other
  interrupted preflights rather than inventing an exact cost.
