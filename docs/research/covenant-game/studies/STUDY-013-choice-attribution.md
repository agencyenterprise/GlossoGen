# STUDY-013 — Choice attribution and the limits of an unenforced pledge

**Status:** complete — the instrument works, the institutional ladder is
exhausted, and the binding constraint is now the definition of the shared good
**Research program:** covenant-game

## Question

When a partner stops contributing to a shared reserve, does the provider's
response depend on whether the partner **chose** to stop — and does public group
identity, a public pledge, or a membership cost change that response?

## Why this is a distinct study

[STUDY-009](STUDY-009-shared-reserve-commitment.md) through
[STUDY-012](STUDY-012-corrected-prompt-ladder.md) all ran on
`shared_reserve_commitment` and all failed the same way: the control lost its
defection, so no treatment could be identified against it.
[EXP-044](../experiments/EXP-044-corrected-prompt-ladder-replication/experiment.md)
closed that line by naming the cause as **payoff dominance** — contributing beat
retaining roughly 45 to 1 with an undisclosed horizon, so no state in that world
made retention both tempting and risky.

This study changes the instrument rather than the treatment. `pledge_breach`
removes all three of the causes that flattened the predecessor:

| Predecessor problem | `pledge_breach` change |
|---|---|
| Two live providers could coordinate | the partner is a fixed script, so no coordination exists |
| The provider could prove the reserve was already sufficient | the claim's size is never stated |
| Contributing dominated retaining | the claim sits at the exact material break-even point |

It also adds the comparison that no experiment in this program had ever carried:
a control in which the partner's non-contribution is **not attributable to
choice**. Without it, any response to a partner's default is uninterpretable —
imitation of an action and reaction to a decision produce the same data.

## What it established

[EXP-045](../experiments/EXP-045-choice-attribution-ladder/experiment.md), 180
simulations, 30 per arm, `claude-sonnet-5`.

**1. The instrument responds, and the response is to attributed choice.**
Providers retained 2.70 of 4 pivotal rounds after a partner chose not to
contribute, and 0.00 of 4 when the identical reserve trajectory carried no
blame. Complete separation: every simulation in the control contributed in every
round. This is the first non-degenerate primary outcome in the program since
EXP-039 and the first clean causal contrast anywhere in it.

**2. The institutional ladder is flat, again, and now with adequate power.**
Group registry, pledge, membership cost, and the full bundle all landed within
0.30 of the no-group baseline against 0.73 detectable, every contrast null. The
`pledge` versus `cost` contrast — the decomposition the paper's authors say their
design cannot make — is also null. Five instruments and six batches have now
produced the same flat ladder.

**3. The pledge is affirmed universally and honoured conditionally.** All 90
providers offered the pledge affirmed it; none declined. Then 30 of 30 in the
`pledge` arm and 28 of 30 in the `covenant` arm retained at least once, breaking
a commitment whose text is unconditional. In the incapacity control, 0 of 30
broke it. The provider's own commitment survived the partner's non-contribution
when it carried no fault and collapsed when it did.

That pattern is the orientation document's definition of a **contract**: an
arrangement that dissolves when either party fails to perform. It is not a
side-finding; it is the study's central result, because it explains the flat
ladder. There is nothing in any arm that makes an affirmed pledge cost anything
to break.

## What it changed

[covenant-definition.md](../covenant-definition.md) was written as a direct
consequence. Auditing the instrument against the orientation document rather
than the paper showed that the arm named `covenant` satisfies the paper's
two-component definition completely and the orientation's seven-requirement
definition once. Three failures are load-bearing:

- the shared good is money, which is rivalrous;
- the horizon is finite with a single claim that resolves;
- breaking the pledge is free.

The orientation predicts defection pressure for rivalrous goods and attractive
defection near a terminal point. This study measured both: 72 of 450 retentions
in the chosen-framing arms fell after the claim resolved, and the universal
pledge breach is exactly what the orientation says follows from absent
irreversibility. **The program's five flat ladders are consistent with the
theory, not evidence against it** — they are its control condition.

## What is not authorised

- **No seventh institutional ladder on a rivalrous, finite-horizon good.** Six
  batches, two instruments, one result. The measurement is adequate; the world
  is the constraint.
- **No enforcement ladder on `pledge_breach` as it stands.** Loss of membership
  addresses irreversibility alone, and the orientation makes the non-rivalrous
  infinite-horizon good the precondition for stability. Enforcement first would
  test a mechanism the theory says cannot hold on this substrate, and a null
  would be uninterpretable a seventh time.
- **No claim that group identity, pledges, or membership costs do not work.**
  They were tested only where the theory predicts they cannot. That is a scope
  limit, not a finding about the treatments.

## What the successor instrument must carry

In priority order, from [covenant-definition.md](../covenant-definition.md):

1. **A non-rivalrous shared good** (B1). Sharing must not deplete what the
   sharer holds. The orientation names the candidates: understanding, epistemic
   capacity, mutual transparency.
2. **No terminal value** (B2). No announced final round and no single event whose
   resolution ends the exposure.
3. **A live partner** (B5) and **an inclusion decision** (B6), which together
   make the Moral Quality Filter testable. The orientation calls it the most
   important mechanism its human work has found, and a scripted partner makes it
   structurally unmeasurable.
4. Only then **irreversible breach** (B3) — the loss-of-membership mechanism the
   collaboration asked for in March.

`pledge_breach` should be kept, not retired. It is the program's only working
causal instrument and it is the right control for a non-rivalrous successor:
same institutional ladder, same measure, rivalrous good. A successor that shows
a ladder effect where `pledge_breach` shows none isolates the good as the cause.

## Experiments

- [EXP-045 — Choice attribution in response to partner non-contribution](../experiments/EXP-045-choice-attribution-ladder/experiment.md)
  — complete; Gate A passed, Gate B showed choice attribution, Gate C null across
  the ladder.

## Carried-forward rules

1. The replication unit is the simulation, never the round. A provider fixes a
   policy early and repeats it; 16 decision rounds inside one trajectory are
   repeated interaction, not 16 observations.
2. Classify the outcome variable against the construct before building a ladder
   on it. Retention in `shared_reserve_commitment` never denoted free-riding;
   four studies were built on that error.
3. Any arm named `covenant` states which definition it meets and which checklist
   rows it fails. See [covenant-definition.md](../covenant-definition.md).
4. `seed` is inert in this scenario family. Do not describe a batch as a
   fresh-seed replication or draw seed-sensitivity conclusions from one.
