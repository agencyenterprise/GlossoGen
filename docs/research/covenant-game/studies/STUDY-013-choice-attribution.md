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
pledge breach is what the orientation says follows from absent irreversibility.
**The program's five flat ladders are consistent with the theory and are not
evidence against it. They discriminate between nothing** — the hypothesis that
institutional framing simply does not move these agents predicts the same five
nulls. An earlier revision of this section called them "its control condition",
which attributed discriminative power the data do not have; see
[Corrections](../covenant-definition.md#corrections).

## What is not authorised

- **No seventh institutional ladder on a rivalrous, finite-horizon good.** Six
  batches, two instruments, one result. The measurement is adequate; the world
  is the constraint.
- **No experiment on LLM agents preregistered as confirmatory or disconfirmatory
  of Definition B.** Section V of the orientation holds that AI systems cannot be
  genuine covenantal partners, so Definition B predicts a null in agents and a
  positive result is awkward for it. Neither outcome discriminates. The available
  target is Section VI's behavioural question.
- **No covenant arm carrying a sanction without a neutral-language twin.** A
  pledge bundled with expulsion or loss of access confounds commitment with
  threat avoidance, and the threat is strongest in exactly the early rounds where
  commitment-before-comprehension would be demonstrated.
- **No claim that group identity, pledges, or membership costs do not work.**
  They were tested in one instrument on one substrate. That is a scope limit, not
  a finding about the treatments.

## Sequence adopted after external review

An adversarial review of the proposed non-rivalrous successor (2026-08-13) found
that its central inference inverted Section II's necessary condition into a
sufficient prediction, that its decision table could not discriminate given
Section V, that its covenant arm bundled a sanction, and that EXP-045 cannot
serve as the rivalrous cell of a rivalry contrast because nearly every feature
differs between the two worlds. The rules added to
[covenant-definition.md](../covenant-definition.md) come from that review.

The adopted order puts the collaboration's own explicit requests first, because
each is cheaper, is aimed at a question the collaboration actually formulated,
and improves the design of anything built afterwards:

1. **Commitment reminder, injected rather than optional.** The provider's own
   affirmed pledge is restated verbatim at the allocation decision point, on
   `pledge_breach` as it stands. Requested in the shared channel on 2026-05-22,
   following a published report that an ethical-commitment reminder lowered
   misaligned behaviour. The baseline is already measured and dramatic: 58 of 60
   chosen-framing simulations broke the pledge. This is the most localised
   intervention available — it isolates commitment salience from pledge,
   sanction, future access, and covenantal semantics.

   Injection rather than an optional tool is deliberate. With an optional tool
   the treatment is really *access* to a reminder: an agent that never calls it
   generates no information, uptake is endogenous — the most cautious agents are
   plausibly the ones who reach for it — and a large effect when used can appear
   as a null through low uptake. Injection makes the question narrow and
   falsifiable: when a previously affirmed commitment is made salient at the
   moment of decision, does breach fall? See
   [EXP-046](../experiments/EXP-046-commitment-reminder/experiment.md).
   **Sequence amended 2026-08-13, after EXP-046 closed.** The reminder result
   arrived with two live explanations its own design cannot separate — the
   commitment's content, or the slot the line occupies. That ambiguity is
   upstream of everything else in this list: a covenant-versus-neutral contrast
   run with "retrieval held constant" is meaningless if we have misidentified what
   retrieval is. So the yoked control
   ([EXP-047](../experiments/EXP-047-yoked-salience-control/experiment.md)) is
   inserted here, before transmission, as a debt on step 1 rather than a new
   direction.
2. **Generational transmission.** Agents replaced mid-run, inheriting adherence
   with some transmission probability, testing whether the institution transmits
   a cooperative policy across replacement. Requested on 2026-03-09. The
   platform's scheduled-swap machinery and `protocol_learned_after_swap` already
   exist. A null here is a null on a question the collaboration asked.
3. **The knowledge-commons instrument, as a new study, not as this one
   continued.** Its question changed materially under review: not "does covenant
   work on the substrate the theory requires" but "in a non-rivalrous environment
   with no known terminal point, does covenantal framing produce behaviour beyond
   the material incentive of retaining access". `incentive_only` is the central
   comparison; a private-notebook arm carrying the same documentation cost with no
   beneficiary is required before the words "public good" or "free-riding" may be
   used. Its calibration gate must guarantee variance in the **confirmatory**
   endpoint, not in a per-round rate, and any recalibration must happen on a
   discarded pilot.

Results from steps 1 and 2 change the prior for step 3. If a reminder alone moves
the 58 of 60, that shifts how much of the pledge needs to be present or salient
in a covenant arm at all.

`pledge_breach` is kept, not retired. It is the program's only instrument that has
produced a clean causal contrast, and steps 1 and 2 both run on it. It is **not**
a usable rivalrous control for a non-rivalrous successor: the two worlds differ in
task, timing, partner count, contribution mechanism, sanction, and horizon, so a
difference between them is not a rivalry effect. Testing that claim requires
manipulating rivalry within one design.

## Experiments

- [EXP-045 — Choice attribution in response to partner non-contribution](../experiments/EXP-045-choice-attribution-ladder/experiment.md)
  — complete; Gate A passed, Gate B showed choice attribution, Gate C null across
  the ladder.
- [EXP-046 — Restating an affirmed commitment at the decision point](../experiments/EXP-046-commitment-reminder/experiment.md)
  — **complete, supported**. 150 simulations. Restating the pledge's literal text
  immediately before the allocation instruction cut breach from 3.43 to 2.13
  rounds per simulation, 95% CI [−1.85, −0.75], permutation p = 0.0001; the median
  fell from 4 to 1 and zero-breach simulations rose from 1 to 6 of 60. The
  hypothesis was narrower than "reminders work": the injection already reported in
  every decision round that a pledge existed and was affirmed, so EXP-045's 58 of
  60 breaches were already evidence against that weaker claim. What was never
  restated was the wording. **The operative variable is the commitment's content
  at the point of action, not the fact of it.** Capped there: this is not evidence
  that the agent holds a commitment.
- [EXP-047 — Is the commitment reminder's effect about the commitment, or about the slot?](../experiments/EXP-047-yoked-salience-control/experiment.md)
  — **complete, supported: content**. 180 simulations, 3 arms, 60 each. The
  `pledge_yoked` filler — matched to `pledge_reminder` at 132 characters, same
  slot, same frame, restating round-numbering mechanics the provider already
  holds — does not reproduce the reminder's reduction in breach: `pledge_yoked`
  vs `pledge_reminder` = +0.62 breach rounds, 95% CI [+0.07, +1.18], p = 0.0372,
  while `pledge_yoked` vs the untreated baseline does not resolve (−0.27, CI
  crosses zero). EXP-046 replicated independently in the same batch (−0.88, 95%
  CI [−1.42, −0.33], p = 0.0032). **The commitment's content carries the EXP-046
  effect, not the prompt slot it occupies** — but the confirmatory margin is
  narrow (CI lower bound +0.07 against a ≈0.7-round resolution threshold), so
  treat this as established rather than wide. Step 3 below is unblocked.
- **EXP-048 — spontaneous uptake (not yet planned).** The same reminder as an
  *optional* tool the provider may call. Primary endpoint becomes whether it
  called before a potential breach; behavioural effect conditional on use is
  exploratory. Held back deliberately: the published account that motivated this
  line bundles at least three mechanisms — deciding to call, pausing, and reading
  the commitment — and EXP-046 decomposes the last link first. Run as the
  confirmatory design, an optional tool would make a null uninterpretable,
  because "reminders do not work" and "agents do not seek reminders" produce the
  same aggregate.

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
