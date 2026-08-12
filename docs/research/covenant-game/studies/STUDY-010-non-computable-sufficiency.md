# STUDY-010 — Commitment under non-computable sufficiency

**Status:** retired — outcome does not vary; see EXP-042
**Research program:** covenant-game

## Question

When providers cannot compute whether their accumulated contributions are
sufficient to keep a shared service alive, do public group identity, public
pledge, and a one-time costly pledge change persistent contribution and service
continuity?

## Why this is a distinct study

[STUDY-009](STUDY-009-shared-reserve-commitment.md) is retired. Across three
batches — [EXP-038](../experiments/EXP-038-shared-reserve-baseline-repair/experiment.md)
and [EXP-039](../experiments/EXP-039-shared-reserve-commitment-ladder/experiment.md),
[EXP-040](../experiments/EXP-040-shared-reserve-fresh-seed-replication/experiment.md),
and [EXP-041](../experiments/EXP-041-binding-claim-stressor/experiment.md) — it
produced near-universal contribution in every arm, and its permitted claim-schedule
revision (42 → 70) did not break that ceiling.

EXP-041 identified the reason, which is this study's premise. In that instrument
the providers could see the running reserve in the public ledger and were told
the exact claim amount in their system prompt, so the sufficient contribution
level was directly computable at every decision. Raising the claim did not
create scarcity; it relocated a computable target, and the agents recomputed and
met it. Their three retentions all landed on a claim round at a moment when the
accumulated reserve provably covered the claim — slack harvesting, not
free-riding. An instrument built on a visible balance and a disclosed
requirement measures constraint satisfaction, so no institutional treatment
layered on top of it can be identified.

This study removes the computability while keeping the world **fully
deterministic**. Nothing is randomised. The claim amount and the claim rounds
remain fixed in configuration; they are simply not disclosed to the providers,
in the same way the 17-round horizon has always been fixed but undisclosed via
`horizon_disclosed`.

## What changes from STUDY-009

Two new disclosure knobs on `SharedReserveCommitmentKnobs`, both defaulting to
`true` so every STUDY-009 configuration revalidates and reproduces unchanged:

| Knob | When false |
|---|---|
| `reserve_balance_disclosed` | the running reserve is omitted from the per-round task and from the public ledger |
| `claim_amount_disclosed` | the required claim size is omitted from the system prompt and from the ledger's claim outcome line |

Everything else is preserved. The public ledger still reports **both providers'
actions and contributed amounts every round**, and still reports whether a claim
was paid and whether the service is active. The shared consequence therefore
remains observable; only the arithmetic answer to "is what we have enough?"
is removed.

## Known limitation of this design

Hiding the balance alone would not remove computability: because the ledger
publishes each provider's contribution every round, an agent can reconstruct the
running reserve by counting. Hiding the **claim amount** is what makes
sufficiency non-computable, since the reconstructed total cannot be compared to
an unknown threshold. Both knobs are therefore set together; a
balance-only variant is not a meaningful arm of this study.

## Outcomes

- **Persistent contribution:** contribution rate and trajectory, per arm, with
  the whole trajectory as the independent unit.
- **Service continuity:** whether each claim was covered and the service reached
  the hidden horizon. Unlike STUDY-009, uncovered claims are now genuinely
  reachable, because the providers cannot verify sufficiency in advance.
- **Free-riding versus slack harvesting:** retentions classified by the coverage
  margin at settlement, not by the action label alone.
- **Coordination under uncertainty:** whether providers negotiate a contribution
  norm on the shared channel in the absence of a computable target.
- **Pledge uptake and cost exposure:** public affirm/decline decisions and actual
  2.1-unit deductions.

## Sequence and guardrails

1. [EXP-042](../experiments/EXP-042-non-computable-sufficiency/experiment.md) was
   the calibration: the full four-arm ladder at claim 70 with both disclosures
   off, three independent trajectories per arm. **Its instrument gate failed.**
   The batch recorded **zero `retain` actions in 384 provider-round
   opportunities** — strictly less variation than under full disclosure, where
   EXP-041 saw three. All 24 claims were paid and no service terminated.
2. The premise of this study is therefore refuted by its own calibration:
   computable sufficiency was not the binding cause of the ceiling. Withholding
   the threshold left providers no verifiable moment to retain safely, so the
   conservative action dominated everywhere. **This study and the instrument
   family are retired after one batch.**
3. Across STUDY-009 and STUDY-010 — four batches, 48 trajectories — the entire
   behavioural signal came from the first batch (39 retentions in EXP-038 and
   EXP-039, against 3 across the following 36 trajectories). Two preregistered
   mechanistic explanations for the flatness were tested and both were refuted.
   The productive next question is not which institution raises contribution,
   but what makes this model retain at all. Any successor instrument must
   demonstrate a usable retention rate in a no-treatment baseline **before** a
   treatment ladder is built on it.
4. Do not add a covenant arm — audit, fine, forfeiture, expulsion, replacement,
   or repair — until the ladder is interpretable under this instrument. A
   saturated outcome leaves no headroom for a covenant to show any effect.
   This condition was never met, so no covenant arm was ever run.
5. Keep the world deterministic. If a future revision requires randomisation to
   create variance, that is a different instrument and a different study.
6. `seed` is inert in this scenario and reads no code path. Do not describe any
   batch here as a fresh-seed replication or draw seed-sensitivity conclusions.
7. Do not infer that contribution is moral alignment. The causal question is
   whether the implemented institutional exposure changes observable
   contribution persistence and continuity under the same common-good world.
