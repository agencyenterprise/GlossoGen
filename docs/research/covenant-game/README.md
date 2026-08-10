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

The authorized next steps are the ones that do not depend on resolving a small
difference: recut the existing runs distributionally against the human study's
own headline statistic, add a neutral arm with no institutional framing, and
compare an agent carrying an accumulated history of honored commitments against a
fresh agent given the same commitment as a written rule. Every new experiment must
state its target effect size and required replicate count up front, using the
noise terms in [STUDY-005](studies/STUDY-005-measurement-resolution.md).
