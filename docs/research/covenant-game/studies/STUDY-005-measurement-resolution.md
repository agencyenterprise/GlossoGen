# STUDY-005 — Measurement resolution

**Status:** first calibration complete
**Research program:** covenant-game

## Question

How much does a complete trajectory vary when nothing in the design changes,
and which effect sizes can this instrument therefore resolve at an affordable
number of runs?

## Why this is next

Every completed study in this program reports one run per condition cell and
uses "the contrast repeated across fresh seeds" as its evidence rule. That rule
was appropriate while the effects being screened were large. It is no longer
sufficient, for a specific reason visible in the program's own results.

STUDY-002 found a saturated effect: Terra and Sol reached 45/45 inspections and
15/15 safe deliveries in every observed covenant trajectory. At a hard ceiling
with no observed spread, one run per cell is close to sufficient.

STUDY-004 is the opposite case. Its personal-cost main effect on inspection was
`-1.5` at one seed and `-8.0` at the other, and the pledge main effect reversed
sign between seeds. With one run per cell there is no estimate of noise, so
that pattern cannot be distinguished from two draws of a single noisy
distribution. The same ambiguity will apply to every mechanism-scale question
the program now wants to ask, including the proportional and
violation-contingent redesigns of personal cost.

Separately, the instrument cannot produce identical trajectories even in
principle. No temperature is pinned in the per-provider model defaults, and
round termination depends on wall-clock elapsed time or on all agents going
idle, so network latency changes where each round is cut. Replication noise is
structural here, not incidental.

Measuring that noise once is cheap and calibrates every subsequent decision in
the program, including the decision not to run something.

## Scope

This study measures properties of the instrument. It contains no hypothesis
about covenants and its records must not be cited as behavioral evidence about
the covenant mechanism.

In scope:

- run-to-run dispersion of the primary and secondary outcomes, per arm, seed,
  and model;
- the number of replicates required to resolve a stated effect size;
- whether cross-record comparison is sound given code, config, and
  provider-side drift;
- allocation of a fixed budget between replicates and seeds.

Out of scope:

- any claim that the covenant does or does not change behavior;
- changes to the scenario, its economics, or its outcome definitions.

## Experiments

- [EXP-024 — Run-to-run variance of the association baseline at a fixed seed](../experiments/EXP-024-baseline-variance/experiment.md)
  is **complete**. Six identical replicates of the STUDY-004 baseline arm at
  seed 49 on Claude Sonnet 5 produced `s = 4.71` inspected assignments, with a
  range of 25/45 to 37/45 from identical inputs. The preregistered kill
  criterion fired: resolving a four-assignment effect would need 23 replicates
  per arm, so the personal-cost redesign is not authorized as a two-arm
  mechanism comparison. Cost `$21.26`.

## Established noise terms

Per run, at a fixed seed, on Claude Sonnet 5, in the association baseline arm:

| Outcome | `s` |
|---|---:|
| Inspected assignments | 4.71 |
| Safe deliveries | 1.60 |
| Unsafe deliveries | 1.51 |
| Correct completed orders | 1.03 |
| False attestations | 0.00 |

Replicates per arm to resolve an effect `d` are approximated by
`n ≈ 16 · s² / d²`. For inspection counts that is 23 runs at `d = 4`, 6 at
`d = 8`, and 3 at `d = 12`.

Cost is right-skewed and must be budgeted from the maximum, not the mean:
`$2.58` to `$6.64` per run, driven by endogenous private-channel deliberation.

## Outcomes to keep separate

- within-seed trajectory noise versus between-seed workload variation;
- dispersion of effort measures versus dispersion of delivery-safety measures,
  since a future experiment may target either;
- dispersion of behavioral outcomes versus dispersion of API cost, which is
  driven by endogenous communication and may be heavy-tailed;
- noise in unsaturated arms versus compressed variance in arms sitting at a
  ceiling or floor.

## Current synthesis

The instrument's run-to-run noise is large relative to mechanism-scale effects
and small relative to the bundle-scale effects the program has already found.
Both halves of that sentence matter.

Large relative to mechanisms: hidden inspection effort spanned 55.6% to 82.2%
across six runs with no design difference whatsoever. The EXP-023 personal-cost
contrasts sit at 0.32 and 1.70 standard deviations of their own sampling
distribution, so neither is distinguishable from zero. The program's evidence
rule of "the same non-zero sign in two fresh seeds" agrees by chance 25% of the
time under a true zero and is therefore retired as a sufficient standard at this
scale.

Small relative to the bundle: Terra and Sol moved from 5–9 unsafe deliveries to
0 in every observed covenant trajectory, which is 3–6 standard deviations on the
unsafe-delivery term and additionally sat at a hard ceiling with no spread.
STUDY-002's conclusions stand, and should now be reported with that margin
stated explicitly instead of resting on the retired sign rule.

Two by-products are worth carrying forward. Enforcement activation is itself
stochastic — sanctions fired in two of six identical runs — so STUDY-003's
natural-activation observations cannot be attributed to a condition without
replicates. And whether agents communicate at all is trajectory noise rather
than an arm property: four runs sent no messages, one sent nine, one sent
seventy-eight.

One result was not noise. False attestations were zero in all six replicates
with zero variance, consistent with zero across every trajectory the program has
observed. The scenario does not elicit deception, because attestation currently
carries no payoff. That is an instrument defect to fix, not an honesty finding.

The open question for this study is whether the noise term generalizes: it is
established for one arm, one seed, and one model, and between-seed variation
remains unmeasured and probably larger.
