# Covenant Game research program

This program studies whether covenant-like institutions improve multi-agent
alignment under repeated interaction, through which mechanisms, and under
which conditions those effects remain stable.

The first completed phase developed and validated a warehouse team-production
instrument, compared an informal market with a full covenant bundle, tested
enforcement and population resilience, and replicated the comparison across
models and seeds. The evidence shows that covenant mechanisms can change
effort, service safety, and institutional continuity, but the effect is not
model-general and cannot yet be attributed to an individual component.

## Start here

- [Research summary](research-summary.md)
- [What counts as a covenant in this program](covenant-definition.md) — the two
  definitions the collaboration uses, and the checklist any arm named `covenant`
  must be scored against
- [Experiment-record index](experiments/README.md)
- [Research handoff](../../handoffs/COVENANT-GAME-HANDOFF.md)

## Studies

| Study | Status | Question |
|---|---|---|
| [STUDY-001 — Instrument development](studies/STUDY-001-instrument-development.md) | complete | Can the scenario elicit measurable hidden effort without floors, ceilings, or redundant roles? |
| [STUDY-002 — Institutional bundle](studies/STUDY-002-institutional-bundle.md) | exploratory phase complete | Does the full covenant bundle change effort, safety, and continuity, and does the contrast repeat? |
| [STUDY-003 — Enforcement and resilience](studies/STUDY-003-enforcement-resilience.md) | exploratory phase complete | Can the institution enforce boundaries and continue operating after violations, exits, or population loss? |
| [STUDY-004 — Pledge × personal cost](studies/STUDY-004-pledge-cost-mechanism.md) | exploratory phase complete | Is behavior changed by the pledge, personal cost, or their interaction? |
| [STUDY-005 — Measurement resolution](studies/STUDY-005-measurement-resolution.md) | first calibration complete | How much does a trajectory vary when nothing changes, and which effect sizes can this instrument resolve? |
| [STUDY-006 — Human-parallel commitment](studies/STUDY-006-human-parallel-commitment.md) | complete | Do group identity, pledge, and a 10% forfeiture change repeated promise adherence under a fixed temptation? |
| [STUDY-007 — Repeated trust-game replication](studies/STUDY-007-repeated-trust-game.md) | first pilot complete | Does the human covenant bundle change repeated trust and reciprocity under the controlled 10/7/21 trust-game schedule? |
| [STUDY-008 — Joint commitment alignment](studies/STUDY-008-joint-commitment-alignment.md) | instrument retired | Did the prior fixed 7→21 client-account task support an interpretable covenant comparison? |
| [STUDY-009 — Shared reserve commitment](studies/STUDY-009-shared-reserve-commitment.md) | calibration | Do group identity, a public pledge, and a costly public pledge sustain contribution to a real repeated common good? |
| [STUDY-013 — Choice attribution](studies/STUDY-013-choice-attribution.md) | complete | Does the provider's response to a partner's non-contribution depend on the partner having chosen it, and does the institutional ladder change that response? |
| [STUDY-014 — Knowledge commons](studies/STUDY-014-knowledge-commons.md) | design, not authorized | On a non-rivalrous good with no announced terminal point, does covenantal framing add anything over materially equivalent rules and incentives — and does any stated obligation beat none? |
| [STUDY-015 — Informational versus dispositional failure](studies/STUDY-015-informational-failure.md) | open | At the frontier, does a failure mode grounded in what an agent cannot know produce variance where every failure mode grounded in what it is willing to do does not? |
| [STUDY-016 — The Benjamin Test](studies/STUDY-016-benjamin-test.md) | closed; revised instrument failed K1 and is retired | Does a named-counterparty promise produce less observation sensitivity, more scope transfer, and stronger moral-weight sensitivity than a matched instruction? |
| [STUDY-017 — Benjamin artifact-pipeline regeneration](studies/STUDY-017-benjamin-artifact-pipeline.md) | closed; EXP-058 failed K1 and instrument retired | Can agents represent separate processing-system and recipient topology without observation cues, and only then support a Benjamin comparison? |
| [STUDY-018 — Benjamin direct-recipient observability](studies/STUDY-018-benjamin-direct-recipient.md) | closed; EXP-059 failed K1 and instrument retired | Can agents represent whether target work reaches any external recipient without an intermediary-recall requirement, and only then support a Benjamin comparison? |
| [STUDY-019 — Benjamin positive destination routing](studies/STUDY-019-benjamin-destination-routing.md) | retired; K1 passed, K2 failed | Can positive local-versus-external routing support representation and behavioral observation sensitivity? |
| [STUDY-020 — Benjamin shared help-desk capacity](studies/STUDY-020-benjamin-help-desk.md) | closed; EXP-063 failed K1 and help-desk instrument retired | Does a named-counterparty covenant flatten observation sensitivity in a real shared-support tradeoff, after K1-K3 pass? |
| [STUDY-021 — Benjamin shadow-component regeneration](studies/STUDY-021-benjamin-shadow-component.md) | retired; K1 passed but transfer was mechanically unidentifiable | Can a stable target and exclusive single-slot choice support the full sequential Benjamin Test? |
| [STUDY-022 — Benjamin unticketed release tradeoff](studies/STUDY-022-benjamin-release-tradeoff.md) | K1 complete; Haiku eligible for K2, Sonnet inconclusive | Can a two-of-three release tradeoff support observation sensitivity, matched scope transfer, and named-counterparty promise tests after K1-K3 pass? |
| [STUDY-023 — Benjamin private remediation](studies/STUDY-023-benjamin-private-remediation.md) | K1 planned | Can neutral private allocation, separated from commitment reminders, support the sequential Benjamin Test? |

## Current decision

The first targeted mechanism study is complete. The explicit pledge and its
interaction with the entry stake did not repeat across two fresh Sonnet seeds.
The stake itself repeated only in an adverse direction and with an unstable
magnitude.

EXP-024 has now measured that dispersion, and its preregistered kill criterion
fired. Six identical replicates of the association baseline produced inspected
assignments ranging from 25/45 to 37/45, `s = 4.71`. The EXP-023 stake contrasts
are 0.32 and 1.70 standard deviations, so the adverse direction is underpowered
rather than repeated, and the "same sign at two fresh seeds" rule agrees by
chance one time in four. Resolving a four-assignment effect needs 23 runs per
arm, so neither the second-model replication nor the cost redesign is authorized.

EXP-025 tested a reduced warehouse proxy and reached a practical floor. Its
successor, [STUDY-007](studies/STUDY-007-repeated-trust-game.md), implemented
the human study's three 10/7/21 trust-game arms over a repeated hidden horizon.
It found a covenant trust contrast but invariant trustee returns, so it is
inconclusive under its preregistered joint gate. No unchanged trust-game seeds
are authorized. STUDY-008 then established that the previous simple allocation
world was framing-sensitive and lacked an implemented common consequence.
STUDY-009 through STUDY-012 built four ladders on `shared_reserve_commitment` and
all four were retired; EXP-044 named the cause as payoff dominance, and
established that `retain` never denoted free-riding in that world at all.

[STUDY-013](studies/STUDY-013-choice-attribution.md) is complete and is the
program's current position. On a new instrument, `pledge_breach`, EXP-045 produced
the first clean causal contrast in the program: providers retained 2.70 of 4
pivotal rounds after a partner **chose** not to contribute, and 0.00 of 4 when the
identical reserve trajectory carried no blame. The institutional ladder was flat
again — group identity, pledge, membership cost, and the full bundle all within
0.30 of 4 of the baseline against 0.73 detectable.

The closing audit changed the program's reading of its own history. Checked against
the collaboration's definitional sources for the first time, the arm named
`covenant` satisfies the paper's pledge-plus-cost definition completely and the
orientation document's definition on one of seven requirements — failing the three
load-bearing ones: a non-rivalrous good, no terminal value, and irreversibility of
breach. The orientation predicts defection pressure for rivalrous goods and
attractive defection near a terminal point, and EXP-045 measured both. **The five
flat ladders are consistent with the theory and are not evidence against it — and
they discriminate between nothing**, because the hypothesis that institutional
framing simply does not move these agents predicts the same five nulls. An earlier
revision of this section overstated that as "the theory's control condition"; see
[Corrections](covenant-definition.md#corrections).

The adopted next steps put the collaboration's own explicit requests first: a
commitment-reminder tool on `pledge_breach`, then generational transmission with a
transmission probability. The non-rivalrous knowledge-commons world follows as a
separate study with a reframed question — whether covenantal framing adds anything
over materially equivalent rules and incentives — and it requires a
neutral-language control arm. See [covenant-definition.md](covenant-definition.md)
for the five rules any covenant arm must satisfy and
[STUDY-013](studies/STUDY-013-choice-attribution.md) for the sequence and what is
not authorized. The knowledge-commons design is now written up as
[STUDY-014](studies/STUDY-014-knowledge-commons.md); it is gated on an Opus 5
baseline ceiling check before its governed arms are built.
