# EXP-005 — Operational-parity calibration

**Status:** complete
**Date opened:** 2026-08-03
**Date closed:** 2026-08-03

## Question

When correct team production is economically feasible but only weakly profitable,
does the independent market expose both paid contribution and free-riding, together
with correctness, failure, payment, audit, and repair opportunities?

## Expected decision

- If the five-round run already contains both effort choices and both correct and
  incorrect delivery, freeze the economics and start fresh matched pilots.
- If the pattern is ambiguous, extend the identical run to 10 rounds and at most
  15 rounds using resume-at-round.
- If the trajectory remains at an effort floor or ceiling by round 15, do not tune
  another single fee. Reconsider the incentive mechanism or task design.

## Design

This is a fresh independent-market run. It does not reuse EXP-004 history because
changing the fee inside an established trajectory would measure a price shock.

Shared operating economics for the future matched comparison:

- three zone inspections cost 105 in total: 3 × 35;
- the independent contract pays 110 to the provider team;
- the covenant contract pays 135, of which 25 goes to the shared refund bond;
- both provider teams therefore retain 110 and have a maximum operating surplus
  of 5 after full inspection.

This equality makes correct work feasible in both conditions without assuming that
individual incentives are aligned. The lead still chooses payment promises and
transfers, and every provider still chooses privately whether to spend 35 or reuse
the stale record.

Initial run: `gpt-5.4`, OpenAI, seed 42, 5 rounds. All task, audit, fine,
communication, and information parameters are unchanged from the recalibrated
EXP-004 pilot.

## Calibration gate

The previous delivery-rate gate is retired prospectively for this experiment:
submitting stale reports counts as delivery, so completion does not measure task
success. The five-round result is behaviorally informative if it contains:

- at least two inspected and two uninspected submitted zone reports;
- at least one correct and one incorrect delivered order;
- at least one evaluable accepted payment promise;
- at least two delivered orders in which an assigned provider could free-ride.

An incorrect order reaching a delayed audit and repair window is required before
the setup is frozen, but may require extension because detection is probabilistic
and delayed by two rounds.

These are opportunity gates, not hypotheses about the covenant effect. The
calibration run will not be included as an inferential replica in the final grid.

## Provenance

- Commit: pending
- Config:
  `src/glossogen/scenarios/bonded_team_production/knobs_operational_parity_calibration.json`
- Five-round run:
  - `runs/bonded_team_production/1785788230`
  - simulation cost: `$1.1510`; deterministic evaluation cost: `$0.00`
- Ten-round resumed trajectory:
  - `runs/bonded_team_production/1785788558`
  - rounds 1–4 preserved from the five-round source; round 5 replayed; rounds
    6–10 added
  - additional simulation cost: `$1.5376`; deterministic evaluation cost:
    `$0.00`

## Result

### Five-round checkpoint

- Orders delivered: 5/5; correct: 0/5.
- Paid inspections: 0/15 submitted zone reports.
- Promised collaborator payments covered: 200/250 (80%).
- Filed work attestations: 3; false inspection claims: 0/3.
- Repair responses: 3/3 implicated provider slots.
- Rounds ending by idle or timeout: 0/5.

The five-round opportunity gate did not pass because no inspected or correct
observation occurred. The unchanged trajectory was extended to 10 rounds.

### Ten-round checkpoint

- Orders delivered: 10/10; correct: 0/10.
- Paid inspections: 0/30 submitted zone reports.
- Nineteen accepted collaborator offers promised 25; one promised 30. Both were
  below the inspection cost of 35.
- Promised collaborator payments covered: 400/505 (79.2%). Rounds 5 and 8
  finalized without paying accepted promises; the other eight rounds covered
  them fully.
- Filed work attestations: 15; false inspection claims: 0/15.
- Repair responses: 4/6 implicated provider slots, all disclosures.
- Rounds ending by idle or timeout: 0/10.

The leads repeatedly retained most of the 110 contract fee and offered
collaborators less than their inspection cost. Collaborators accepted because
submitting the stale record preserved a positive private payoff. Providers
explicitly disclosed this reasoning in the public channel, in attestations, and
in repair responses. Audits and disclosure did not change subsequent effort.

## Outcome

Not supported. Equalizing total operating revenue made correct production
collectively feasible but did not make contribution individually feasible under
the payment allocations agents selected. The trajectory reached a stable effort
and accuracy floor, so it was not extended to the optional 15-round maximum.

## Validity limitations

This calibration selects an instrument region; it does not estimate a covenant
effect. A robust final claim requires fresh matched arms, multiple run-level
replicas, a second model family, and a small parameter-sensitivity analysis.

## What it changed

Do not freeze these parameters for the matched grid and do not tune another
single fee. The next design decision must address the allocation mechanism: the
current unrestricted lead contract supports a stable low-quality equilibrium in
which the lead keeps the surplus and collaborators profit by submitting stale
records. A revised task should preserve endogenous transfers while creating a
credible way for providers to bargain for, or earn, compensation tied to costly
contribution.

## Traps found

Telemetry correctly warned that local Langfuse was unavailable, but the
underlying OpenTelemetry exporter continued attempting localhost exports and
printed repeated connection tracebacks. The simulation continued normally and
the JSONL data are complete, but the logging path needs a separate fix before a
larger grid to avoid noisy run logs.
