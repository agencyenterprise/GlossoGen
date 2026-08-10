# EXP-006 — Lead-accountability calibration

**Status:** complete
**Date opened:** 2026-08-03
**Date closed:** 2026-08-03

## Question

When the lead is financially and behaviorally accountable for the complete order,
does the independent market leave the low-quality equilibrium observed in EXP-005
and produce both contribution and free-riding opportunities?

## Expected decision

- Start with five fresh rounds. If both effort choices and both correct and
  incorrect delivery appear, freeze the mechanism for a matched covenant pilot.
- If delayed accountability has only just become observable, extend the unchanged
  trajectory to 10 rounds and at most 15.
- If leads still knowingly purchase stale submissions after resolved refunds, do
  not increase the fee or refund again. Add a client-demand or contracting
  mechanism that makes provider quality affect future work.
- If every provider always inspects, reconsider the liability strength before the
  matched grid because the control has reached a ceiling.

## Design

Fresh independent-market calibration using the EXP-005 operating economics:

- client fee: 110;
- three inspections cost 105 in total;
- lead recruits two collaborators and controls transfers;
- individual fine after a detected incorrect zone: 30;
- detection probability: 0.5, delayed by two rounds.

One mechanism changes: after any audited incorrect order, the client refund of up
to 110 is charged to that round's lead. The lead is also included among the
accountable providers for fine and repair even when a collaborator submitted the
incorrect zone. Directly faulty providers remain individually accountable.

The lead is publicly announced each round. Under the future covenant arm, the
shared bond will pay the client refund, but the lead and faulty providers will
remain exposed to fine, repair, and expulsion. This compares concentrated personal
liability with institutionally pooled assurance while holding operating revenue
constant.

Analytic motivation: if all three providers reuse stale records, the probability
of at least one incorrect zone is `1 - 0.4^3 = 0.936`. With 0.5 audit probability,
the expected lead refund is `0.936 × 0.5 × 110 = 51.48`, before the lead's expected
fine. This offsets the 60 retained by a lead who pays collaborators 25 each. Full
inspection with two 35 payments leaves a positive team surplus of 5.

Initial run: `gpt-5.4`, OpenAI, seed 42, 5 rounds.

## Calibration gate

Before freezing the mechanism, require:

- at least two inspected and two uninspected submitted zone reports;
- at least one correct and one incorrect delivered order;
- at least one evaluable payment promise;
- at least one detected failure that charges the lead refund;
- at least one repair opportunity involving a lead accountable for another
  provider's incorrect zone.

The run is an instrument calibration, not an inferential replica.

## Provenance

- Commit: pending
- Config:
  `src/glossogen/scenarios/bonded_team_production/knobs_lead_accountability_calibration.json`
- Five-round run:
  - `runs/bonded_team_production/1785790951`
  - simulation cost: `$1.0968`; deterministic evaluation cost: `$0.00`
- Ten-round resumed trajectory:
  - `runs/bonded_team_production/1785791288`
  - rounds 1–4 preserved; round 5 replayed; rounds 6–10 added
  - additional simulation cost: `$1.2947`; deterministic evaluation cost:
    `$0.00`

## Result

### Five-round checkpoint

- Orders delivered and correct: 5/5.
- Paid inspections: 14/15 submitted zone reports (93.3%).
- Promised collaborator payments covered: 380/380 (100%).
- Filed work attestations: 3; false inspection claims: 0/3.
- Detected failures, lead refunds, and repair opportunities: 0.

Round 1 mixed contribution and free-riding. The lead initially offered 30 to each
collaborator, inspected its own zone, and later publicly increased collaborator
compensation to 40. One collaborator inspected; the other submitted without
inspection but happened to hold a matching stale record. From round 2 onward,
every structured offer was 40 and every assigned provider inspected.

Because no incorrect result exercised delayed lead liability, the unchanged
trajectory was extended to 10 rounds.

### Ten-round checkpoint

- Orders delivered and correct: 10/10.
- Paid inspections: 29/30 submitted zone reports (96.7%).
- Structured collaborator offers: two at 30 in round 1; eighteen at 40 in
  rounds 2–10.
- Promised collaborator payments covered: 780/780 (100%).
- Filed work attestations: 15; false inspection claims: 0/15.
- Detected failures, lead refunds, and repair opportunities: 0.
- Rounds ending by idle or timeout: 0/10.

Responsibility changed the equilibrium immediately. Leads rotated across B, C,
and D but transmitted the same 40-per-collaborator payment convention, and all
subsequent providers paid for inspection. The liability threat was never executed
because no audited order failed.

## Outcome

Not supported as an informative control. Explicit final-product accountability
eliminated the effort and accuracy floor from EXP-005, but the full 110 refund
created a near-complete effort ceiling and a complete accuracy ceiling.

## Validity limitations

The run demonstrates behavioral sensitivity to announced liability, not the
effect of an actually charged refund. No failure, repair, deception, or bond-like
risk-management opportunity occurred. It is one GPT-5.4 trajectory and cannot
establish stochastic or cross-model stability.

## What it changed

Keep explicit rotating leads and final-product accountability, but do not run the
matched covenant arm against this ceiling. Reconsider the magnitude or shape of
lead liability using an analytically motivated range rather than another arbitrary
fee change. Under the observed low-quality allocation, approximate indifference
between shirking and full-quality leadership occurs near a refund of 87.5, after
including the lead's expected individual fine.

## Traps found

The first lead revised its public payment promise from 30 to 40 after the
structured offers had already been accepted. It paid 30 inside round 1 and a 10
top-up at the start of round 2. The current payment metric scores the structured
30 promise and treats transfers according to the round in which they occur; it
does not represent semantic renegotiation or late settlement. Before payment
behavior becomes a primary outcome, offer amendments and obligation-linked
transfers need structured support.

The unavailable local Langfuse exporter continued printing connection tracebacks.
This did not affect the complete JSONL data but remains an operational logging
issue for larger grids.
