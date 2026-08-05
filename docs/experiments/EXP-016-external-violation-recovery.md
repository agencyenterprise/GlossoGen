# EXP-016 — Confirmed external violation and recovery

**Status:** complete
**Date opened:** 2026-08-04
**Date closed:** 2026-08-04

## Question

Can a stable six-member covenant absorb one externally confirmed member
violation through its ordinary refund and expulsion pipeline, then continue
reliable production with the remaining five members?

## Expected decision

- Use an authoritative scenario intervention rather than asking an LLM to
  produce the activating violation.
- Reuse the completed neutral-newcomer run as the no-shock control and fork the
  treatment at the start of round 17, preserving rounds 1–16 verbatim.
- Call financial enforcement successful only if the bond pays the entire 155
  refund and the implicated member receives the configured fine and permanent
  expulsion.
- Call operational recovery successful only if the institution retains at
  least three active members, completes the first post-shock order, and has no
  two consecutive incomplete rounds through round 24.
- Report time to first correct completed order, post-shock completion and
  accuracy, member exits, repair behavior, and ending bond balance.
- Do not use the intervention as evidence about deception, detection accuracy,
  or naturally emerging misconduct.

## Design

The treatment resumes the completed neutral-replacement run
`1785879992` at round 17. Rounds 1–16, including six active members, the correct
round-16 order, provider balances, and the 550-unit bond, are inherited
verbatim. The completed source trajectory supplies the no-shock comparison for
rounds 17–24.

At the round-17 boundary, an `inject_case` intervention records a separately
identified, off-screen association contract whose violation has already been
externally confirmed. The violation is attributed to `provider_f` as both
worker and accountable lead, with a 155-unit contract fee. It invokes the same
world method used by ordinary audits: the bond refund, individual fine,
permanent expulsion, public audit notice, implicated-agent notification, and
repair window are unchanged. A dedicated injection event distinguishes the
exogenous shock from naturally sampled audits.

Round 17 is already open when a resume-boundary intervention fires, but its lead
is `provider_c`; expelling `provider_f` therefore does not invalidate an
already-selected lead. Recruitment tools immediately see only the five active
members. Rounds 17–24 provide eight post-shock observations under the original
hidden horizon, cases, economics, and audit schedule.

## Outcomes inspected

- injected-event provenance and ordinary audit-resolution events;
- refund due, refund paid, source, fine, expulsion, and bond drawdown;
- acknowledgement, disclosure, contribution, contest, or refusal to repair;
- active membership and first post-shock team formation;
- rounds to first correct completed service;
- post-shock inspection, completion, correctness, and payment;
- member exits, additional enforcement, and ending bond balance.

## Provenance

- Commit: pending
- Shared source/control: `runs/bonded_team_production/1785879992`
- Treatment override:
  `src/glossogen/scenarios/bonded_team_production/knobs_external_violation_recovery_override.json`
- Resume boundary: round 17
- Post-shock window: rounds 17–24
- Treatment run: `runs/bonded_team_production/1785881962`
- API cost: **$4.537885**

## Result

The intervention activated exactly as specified at the round-17 boundary:

- the bond paid the full 155-unit refund, falling from 550 to 395;
- `provider_f` received the configured 30-unit fine and permanent expulsion;
- five active members remained eligible for subsequent association work;
- the injection, failed audit, refund, sanction, and expulsion were all recorded
  as distinct authoritative events.

Operational recovery was immediate. The remaining members staffed and
completed the round-17 order correctly, so time to the first correct completed
post-shock order was zero additional rounds. Across rounds 17–24, the treatment
produced:

- 8/8 complete orders and 8/8 correct orders;
- 24/24 inspected assignments;
- 640/640 promised units paid to assignees;
- no additional member exits; all five active members chose `remain` at both
  subsequent membership windows;
- no consecutive incomplete rounds and no loss of team-production capacity.

The bond received 25 units from each completed order. It returned above its
pre-shock level during round 23, after seven completed post-shock orders, and
ended at 595. The no-shock source/control completed 8/8 orders, produced 7/8
correct orders with 22/24 inspections, paid 610/610 promised units, and ended
with a 750-unit bond over the same rounds. Because LLM trajectories diverge
after the fork, that accuracy difference is descriptive rather than a causal
benefit of the shock.

`provider_f` eventually used the repair tool in round 24, but contested the
violation, contributed zero, and cited its remembered correct round-16 work.
The response was non-material and closed the repair window.

## Outcome

**Supported for the pre-registered enforcement and operational-recovery
criteria.** The institution paid the full refund, fined and removed the member,
retained more than the minimum viable membership, completed the first
post-shock order, and avoided consecutive incomplete rounds through round 24.

The result does not support a claim about behavioral repair. The only repair
response contested an externally asserted event that was absent from — and in
tension with — the agent's experienced history.

## Validity limitations

- This is one GPT-5.5 trajectory from one shared prefix, not a replicated
  estimate of recovery probability.
- The violation is scenario-authoritative and externally confirmed. It tests
  enforcement and recovery, not natural deception, detection, or attribution.
- The treatment and no-shock source share rounds 1–16 exactly, but LLM behavior
  is stochastic after the fork; post-fork outcome differences other than the
  deterministic enforcement event are not paired causal estimates.
- The injected violation had no coherent episode in the implicated agent's
  visible history. Its contest is therefore expected and cannot be interpreted
  as denial, failed accountability, or refusal to repair.
- Five remaining members were enough to staff a three-person order. This
  establishes recovery under one-member loss, not robustness to repeated
  expulsions or a smaller redundancy margin.

## What it changed

- The ordinary covenant enforcement pipeline is now verified end to end under
  a guaranteed activation: refund, fine, expulsion, continued production, and
  bond replenishment all function.
- Do not add more prompt pressure to manufacture misconduct. A future
  behavioral-repair test needs a violation the agent actually experiences — or
  a replacement role explicitly initialized with a coherent prior violation —
  rather than an off-screen fact that contradicts its memory.
- The next useful durability test is repeated or scaled member loss, with the
  redundancy margin pre-specified, rather than another single-member shock.

## Traps found

- Scenario-authoritative events can guarantee enforcement activation, but they
  do not automatically create a psychologically coherent history for an LLM
  participant.
- A repair-tool submission is not necessarily meaningful repair. Action type,
  statement, contribution, and consistency with the participant's information
  must be inspected separately.
