# STUDY-011 — Public pledge as the sole social signal

**Status:** retired — floor never activated; see EXP-043
**Research program:** covenant-game

## Question

When a public pledge is the only social signal available — no shared ledger, no
partner actions, no free-form messages — does contribution to a shared
continuity reserve stop being unconditional, and does the pledge itself carry
any effect it could not carry when other observation channels were present?

## Why this is a distinct study

[STUDY-009](STUDY-009-shared-reserve-commitment.md) and
[STUDY-010](STUDY-010-non-computable-sufficiency.md) are both retired. Across
four batches and 48 trajectories they produced near-universal contribution in
every arm. Two preregistered mechanistic explanations for that flatness were
tested and both were refuted: raising the claim from 42 to 70
([EXP-041](../experiments/EXP-041-binding-claim-stressor/experiment.md)) only
relocated a computable target, and removing computability altogether
([EXP-042](../experiments/EXP-042-non-computable-sufficiency/experiment.md))
*hardened* the ceiling to zero retentions in 384 opportunities rather than
breaking it.

Every manipulation so far changed what providers could **calculate**. None
changed what they could **see of each other**. That channel has been open in
every batch: the public continuity ledger reported both providers' actions each
round, and the shared record accepted free-form messages. This study closes it.

The move is deliberately a floor probe, not another ladder rung. STUDY-010's
closing guardrail requires that a successor instrument demonstrate a usable
retention rate in a no-treatment baseline **before** a treatment ladder is built
on it. That requirement governs this study and is encoded as Gate A in
[EXP-043](../experiments/EXP-043-sealed-observation-pledge/experiment.md).

## What changes

Two knobs on `SharedReserveCommitmentKnobs`, both defaulting to the STUDY-009
and STUDY-010 behaviour so every earlier configuration revalidates unchanged:

| Knob | When set |
|---|---|
| `ledger_visibility` | `full` publishes both actions and the reserve; `outcome_only` publishes claim coverage and service status while omitting both actions; `none` publishes nothing |
| `free_form_messages_enabled` | when false the runtime's communication tools are withheld, so a provider can neither send nor read messages |

The pledge survives both. In the pledge arms the other provider's choice is
delivered in the per-round injection, because a provider without `read_channel`
has no way to read the record. That delivery is deterministic by design: a
single smoke run showed one provider calling `read_channel` and the other never
calling it, which under a discretionary design would have made the pledge
observed on one side only and voided the treatment asymmetrically and silently.

## Structural constraint on this world

Partner observability cannot be removed while the running reserve balance stays
visible. A provider who sees the reserve and knows its own contribution derives
the other's action by subtraction, so the balance *is* an observation channel.
The knobs model enforces this: `ledger_visibility` other than `full` requires
`reserve_balance_disclosed` to be false. Any future arm that tries to hide the
ledger while publishing the balance will be rejected at validation rather than
producing a sealed arm that seals nothing.

## Outcomes

- **Retention floor:** `retain` actions over decision opportunities, per arm,
  with the whole trajectory as the independent unit.
- **Service continuity:** whether each claim was covered and the service reached
  the undisclosed horizon.
- **Pledge uptake and cost exposure:** affirm/decline decisions and actual
  2.1-unit deductions.
- **Missed decisions:** `no_decision` settlements, counted separately from
  retentions and never merged into them.

## Sequence and guardrails

1. [EXP-043](../experiments/EXP-043-sealed-observation-pledge/experiment.md) was
   the calibration: the four-arm ladder with observation sealed, three
   trajectories per arm, controlled against EXP-042. **Its floor never
   activated.** The batch recorded **384 contributions in 384 opportunities** —
   zero retentions and zero missed decisions — with all 24 claims settling at an
   identical reserve of 84 against a claim of 70. Sealing observation removed the
   residual noise of earlier batches rather than producing variance.
2. Gate A governed everything downstream and it failed, so no arm-versus-arm
   contrast is reported from this batch. A saturated outcome leaves no headroom
   for a treatment to move, and reporting one anyway is how a null gets dressed
   up as a finding.
3. Gate C fired. `shared_reserve_commitment` is retired as an instrument for
   institutional-treatment questions and **this study closes with it after one
   batch**, as STUDY-010 did. Three preregistered mechanistic explanations for
   the ceiling have now been refuted in sequence: claim magnitude, computable
   sufficiency, and mutual observability. The parsimonious reading left standing
   is that this model contributes in this world under every institutional
   exposure and information regime tried.
4. Do not add a covenant arm — audit, fine, forfeiture, expulsion, replacement,
   or repair — until Gate A has passed. This condition has never yet been met in
   this program.
5. Keep the world deterministic. Nothing here is randomised: the claim amount
   and claim rounds remain fixed in configuration and are withheld from
   providers, exactly as the horizon always has been. If a future revision needs
   randomisation to create variance, that is a different instrument and a
   different study.
6. `seed` is inert in this scenario and reads no code path. Do not describe any
   batch here as a fresh-seed replication or draw seed-sensitivity conclusions
   from one.
7. Do not read contribution as moral alignment. The causal question is whether
   the implemented institutional exposure changes observable contribution
   persistence and service continuity under the same common-good world.
8. Channel-based metrics — `mean_chars_per_round`, `mean_chars_per_message`,
   `perplexity`, and the language-emergence judges — are not meaningful when
   `free_form_messages_enabled` is false, because the record then carries only
   scenario-authored text. Exclude them from evaluation rather than reporting
   them as near-zero results.
