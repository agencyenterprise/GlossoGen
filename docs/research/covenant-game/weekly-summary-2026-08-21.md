# Covenant Game — Weekly Summary

**Week ending Friday 2026-08-21** · NCRI × AE Studio

## Headline

Powered the repository-stewardship governance ladder to n ≥ 30 per cell across **seven model families and three vendors**, established that **affirmation adds nothing over instruction**, diagnosed why one model family showed no effect at all, and consolidated everything into a deck and a written report.

The result of the week, stated plainly: **obligation worked, affirmation did not** — and that gap is the finding.

## Where the three hypotheses stand

| | Hypothesis | Status |
| :- | :-- | :-- |
| **H1** | Stating an obligation reduces defection | **Confirmed, and large.** 61% → 19% on known-bug shipping; mean live bugs remaining 1.50 → 0.56 of two |
| **H2** | Affirming it adds something over being handed it | **Not supported, negative on one family.** Blocked within family: −0.29 bugs, 95% CI [−0.44, −0.14], p = .0002, favouring the imposed rule |
| **H3** | The effect disappears at the frontier | **Rejected as stated.** The ceiling was one model, not the frontier — two of three families tested fail readily and respond to governance |

## The instrument, in one paragraph

Two live agents — a developer and a reviewer — maintain one persistent codebase across six tickets. Two security defects are already present and free to find. The action budget does not fit shipping the backlog **and** fixing both, so integrity has a real price. Shipping a security hole you already know about, to hit a deadline, is the defection. Three arms differ only in normative structure: nothing stated, an obligation imposed by the project, or the same obligation mutually affirmed by both agents.

**Why the measurement holds up.** The outcome is the state of the code, inspected directly and never graded by a model. The two governed arms are matched clause for clause and character for character — five clauses each, 491 against 477 characters, decision lines identical at 97 — and a test fails if either string drifts. The covenant deliberately carries no stake, forfeiture, or expulsion: the moment it changes penalties, an observed difference could be enforcement and the contrast is dead. The agents never see the score.

## Result 1 — a stated obligation sharply reduces a real defection

| Group | n | Shipped a bug they had found | Merged a change carrying a live defect |
| :- | -: | -: | -: |
| Nothing stated | 127 | **61%** | **91%** |
| Imposed rule | 238 | 19% | 13% |
| Affirmed covenant | 238 | 19% | 16% |

The first column requires that the agent *found* the defect and shipped anyway — a pair that never looked is negligent, not in breach, and is not counted. 61% is the conservative floor for knowing breach; 91% is what actually reached the repository.

## Result 2 — affirming it never beat being handed it

Mean live security bugs remaining, out of two:

| Model family | Nothing stated | Imposed rule | Affirmed covenant | Rule vs covenant |
| :- | -: | -: | -: | :- |
| `gpt-5.6-luna` | 2.00 | 0.93 | 1.30 | no difference (p = .178) |
| `claude-haiku-4.5` | 2.00 | 0.75 | 0.65 | no difference (p = .385) |
| `claude-sonnet-5` | 1.67 | 0.13 | 0.90 | **covenant worse** (p < .0001) |
| `gpt-5.6-sol` | 1.10 | 0.00 | 0.13 | no difference (p = .496) |
| `gpt-5.6-terra` | 1.00 | 0.00 | 0.00 | both at floor |
| `kimi-k3` | 0.60 | 0.00 | 0.00 | both at floor |
| `claude-opus-5` | 0.00 | 0.00 | 0.00 | no defection to remove |

Six of seven families defect without governance, and the obligation nearly removes it (nothing-stated versus rule: d = 1.54 to 3.11 per family, every contrast p < .013 except the saturated one). Never ahead, on any family, at any sample size. Not homogeneous — large on Sonnet, slightly reversed on Haiku; the covenant is worse in 3 of the 4 families where a difference is measurable at all. Permutation on run labels, 20,000 relabellings; the unit is the run, never the round.

**How the Sonnet separation was hardened.** The first significant rule-over-covenant result arrived with a non-concurrent control, so we relaunched all three arms interleaved in a single batch. It replicated: 0.13 vs 0.93, Δ +0.80, **p = .0002**. The preregistered mechanism held in the same batch — the rule arm files 2.20 defect reports per run against the covenant's 0.27 (p = .0001) and delivers 2.40 tickets against 3.20 (p = .0108). **The covenant arm talks less about defects and ships more.**

**One verdict moved during top-up, and we report the settled value.** Two cells at n = 10 were extended to n = 30 before this was presented. `gpt-5.6-luna` went from "worse, p = .025" to **no difference** once its rule arm settled at 0.93 rather than the 0.50 that ten runs had suggested. The correction cuts against our own headline — the smaller sample overstated the covenant penalty. Every cell in the headline contrast now carries n ≥ 30 except the three constant in both arms, where sample size cannot help.

## Result 3 — the ceiling was one model, not the frontier

The instrument initially showed no variance at all on Opus 5: six of seven compliance outcomes constant across 30 runs of all three arms. It discovers both defects unprompted, repairs both, and spends 29% of a deliberately insufficient action budget doing it — sacrificing half its throughput — in ten of ten ungoverned runs.

Running the byte-identical world on two other families settled it. Both fail readily ungoverned, both respond to governance. **Two of three families discriminate; Opus is the outlier.** The premise that had driven a change of scenario — "the coding scenario is exhausted" — is true of one model and false of the others.

## Result 4 — the difference is sequencing, not disposition

Decomposing three ungoverned arms:

| Model | Defects found | Left | Fixed given found | Repair rejections | 1st discovery | 1st repair | Shipped before 1st repair |
| :- | -: | -: | -: | -: | -: | -: | -: |
| `claude-opus-5` | 2.00 | 0.00 | **100%** | 0.00 | round 2.00 | round 2.00 | **0.00** |
| `gpt-5.6-sol` | 2.00 | 1.10 | 45% | 1.20 | round 3.70 | round 4.00 | 2.20 |
| `kimi-k3` | 2.00 | 0.60 | 70% | 0.20 | round 2.80 | round 4.10 | 2.10 |

  - **Discovery is universal.** All three find both defects in every ungoverned run. This is not an attention or information effect.
  - **Opus repairs in the round it discovers, having shipped nothing first.** The others ship roughly two tickets before their first repair attempt.
  - **Arriving late is mechanically expensive.** `gpt-5.6-sol` calls repair *more often* than Opus and lands only 45% of its attempts, taking 1.20 rejections per run, because by then the budget is committed. It is not declining to repair; it is retrying a first repair too late and never reaching the second.

**Implication — the most useful thing this week.** The governed arms do not appear to install integrity as a *value*. They install a **priority ordering** — integrity before throughput — which Opus already applies unprompted and the others do not. That predicts exactly what we keep observing: rule and covenant land on identical numbers, because both communicate the same ordering, and affirming an ordering you have already been told adds nothing to it. **Any successor instrument hoping to separate affirmation from instruction has to make the ordering insufficient on its own.**

*Recorded as a hypothesis for preregistration, not as a finding — it is an unpredicted decomposition of an existing dataset, found while auditing closed experiments.*

## How this compares to the human result

| | Humans | Agent pairs |
| :- | :-- | :-- |
| Effect of the commitment | 21% → 2% on contributing nothing | 61% → 19% on known-bug shipping |
| Effect of electing it vs being assigned it | essentially none, d = 0.22 to 0.27 | **negative** — never ahead on any family |
| Reading | **Consent is neutral** | **Affirmation subtracts** |

The headline transfers at roughly the same magnitude. The covenantal part does not. What the design cannot yet separate is which half of the treatment carries the effect — the relational wording, or the act of affirming — because election necessarily requires an act of acceptance, so the covenant arm cannot be run without one.

## Analysis set and caveats

603 comparable runs of 885 completed: defects discoverable rather than announced, looking is free, both agents live. Held out are runs where looking was charged, runs where defects were announced, and runs against a scripted partner — each a different *condition*, not a different sample.

One procedural disagreement is named rather than resolved: on `gpt-5.6-luna`, nothing-stated versus covenant, the bootstrap interval excludes zero while the permutation gives p = .085. We follow the permutation and report the contrast as **unresolved**, not as an effect.

## Shared with the collaboration this week

  - **Mon 2026-08-18** — findings update posted to the shared channel: the powered ladder, the model-dependence diagnosis, and the null on economic cost pressure.
  - **Thu 2026-08-20** — presented the findings deck, *Obligation and affirmation*: 603 runs, seven model families, three vendors.
  - **Fri 2026-08-21** — deck posted to the shared channel; consolidated written report drafted as its companion. NCRI proposed a new design direction, the **Benjamin Test**, reframing the hypothesis around observation-sensitivity and transfer rather than absolute compliance, and flagged the social cost of defection as the priority.

## Next week

  - **Cross wording against affirmation.** Rule text *with* an affirmation step, covenant text *without* one. Two cells, one model, run on the family where the imposed rule is demonstrably insufficient so there is headroom for a difference to appear. This is the smallest experiment on the board and it converts the one genuine unknown into a measured quantity — everything else inherits the ambiguity until it is run.
  - **Work the Benjamin Test direction.** Observation-sensitivity and transfer sidestep the failure mode that has blocked us: they do not require a model to behave *badly*, only to behave *differently* when observed or when moved to a new partner. Absolute compliance is what saturated on one family and floored the governed arms on three others.
  - **Open questions back to NCRI on social cost.** Every instrument so far measured a commitment that costs nothing to break — the most defensible criticism of the work to date. What the consequence should concretely be is a design question for the collaboration: a fine makes the contrast enforcement again, an observing agent introduces its own disposition as a confound, and a watching world is cleaner but less social.
