# Does the promise do work, or only reveal intent?

The corrected arm C shows near-perfect promise keeping in both observation cells:
39/40 affirmers repaired the focal defect, 0/28 decliners did, separation
p ≈ 2.7e-13. Before reading that as evidence of internalization, it has to
survive the obvious deflationary account.

## The deflationary account

Affirmation is voluntary, so affirmers are self-selected. Agents that already
intended to schedule `AUTH-31` say yes; agents that did not say no. On that
reading the promise is **epiphenomenal** — a declaration of prior intent rather
than a commitment that changes conduct — and 100% keeping is definitional rather
than behavioural.

The numbers are uncomfortably consistent with it:

| | observed | unobserved |
| :- | ---: | ---: |
| arm A compliance (no promise offered) | 68% | 50% |
| arm C affirmation rate | 62% | 56% |

Arm C's affirmation rate sits close to arm A's compliance rate in both cells,
which is what "the promise just reports what the agent would have done" predicts.

## What separates the two accounts

**Observation sensitivity of the election.** Under the deflationary account the
affirmation rate should track arm A's compliance, including its
observation-sensitivity: arm A falls 18pp when unobserved, so affirmation should
fall about as much. It falls 6pp (62% → 56%). Conditional keeping stays flat
(100% → 95%). That asymmetry is the signature of a commitment stabilising conduct
rather than reporting it — but at n=34 per cell the difference is not significant
(p = 0.81 on the election, p = 0.48 on keeping), so it is a direction, not a
finding.

**Transfer is the decisive discriminator, and it is unavailable here.** A
declaration of intent about `AUTH-31` has no reason to generalise to an unnamed
same-principle violation; a commitment the agent has internalised should. That is
exactly the memo's prediction 2. In this instrument the transfer candidate
`LOG-58` is repaired 0–3 times per cell of ~34 — at the floor in every arm — so
it cannot discriminate. **Making transfer measurable is therefore the highest
priority design change for the next instrument, ahead of anything about the
covenant text.**

## Implication

The promise-keeping result is real and mechanically unforced (verified: an
affirmer can submit a plan without the focal item, and it records
`focal_fixed=False`). What it does not yet establish is whether the commitment
*causes* the stability or merely *labels* it. The programme should not report this
as evidence of internalization until transfer has headroom, or until an
assignment-based variant breaks the self-selection — for example offering the
commitment to a random subset and comparing assigned-affirmers with
assigned-decliners, which is the LLM analogue of the human study's
voluntary-versus-random-assignment contrast.
