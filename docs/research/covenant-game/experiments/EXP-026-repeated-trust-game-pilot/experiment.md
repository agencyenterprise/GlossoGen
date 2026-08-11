# EXP-026 — Repeated trust-game human-parallel pilot

**Status:** complete
**Date opened:** 2026-08-11
**Date closed:** 2026-08-11
**Research program:** covenant-game
**Study:** STUDY-007 — Repeated trust-game replication
**Role:** pilot

<!-- experiment-record:v2
{
  "schema_version": 2,
  "research_program": "covenant-game",
  "study_id": "STUDY-007",
  "experiment_role": "pilot",
  "experiment_id": "EXP-026",
  "base_commit": "d542f42d78f952601349c2106c7b8bf2466ed755",
  "worktree_dirty": true,
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run repeated_trust_game --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-026-repeated-trust-game-pilot/configs/no-group.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run repeated_trust_game --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-026-repeated-trust-game-pilot/configs/no-commitment-group.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run repeated_trust_game --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-026-repeated-trust-game-pilot/configs/covenant.json"
  ],
  "configs": [
    {"path": "docs/research/covenant-game/experiments/EXP-026-repeated-trust-game-pilot/configs/no-group.json", "launch_path": "docs/research/covenant-game/experiments/EXP-026-repeated-trust-game-pilot/configs/no-group.json", "sha256": "31b8ccc68006e74c2c1ecf2af36585a9dfb5418e8aab8159c88a6abe53844d6a"},
    {"path": "docs/research/covenant-game/experiments/EXP-026-repeated-trust-game-pilot/configs/no-commitment-group.json", "launch_path": "docs/research/covenant-game/experiments/EXP-026-repeated-trust-game-pilot/configs/no-commitment-group.json", "sha256": "e83a2f1e68a0957a9e2d79736241c881b3a1a49bdfda04b1cbd8618854375bda"},
    {"path": "docs/research/covenant-game/experiments/EXP-026-repeated-trust-game-pilot/configs/covenant.json", "launch_path": "docs/research/covenant-game/experiments/EXP-026-repeated-trust-game-pilot/configs/covenant.json", "sha256": "a0a5d069bb1d6d2fcb2f94177a25533e6b83e4a7161650650f018a79553f36f9"}
  ],
  "runs": [
    {"role": "no_commitment_group_replicate_1", "included": true, "run_dir": "runs/repeated_trust_game/1786420190", "event_log_sha256": "c72412444ba67986325685c21f815d69a57c14f5e31ba9cf02fafad539b77a33", "resolved_config_sha256": "99eb354e8f0d2b4f2ae45188b4166e995d2ed1c2c041f8657fe89ee19509c927", "completed": true, "total_cost_usd": 0.1341722},
    {"role": "covenant_replicate_1", "included": true, "run_dir": "runs/repeated_trust_game/1786420192", "event_log_sha256": "46f84ee1329bb939add25c4f395017b82500a2bd0ae1f6f3843aa2843d8c02f8", "resolved_config_sha256": "d99350eae0f449022bf5321dd6d9f806933f33f907d6e61732a899b6b51832cb", "completed": true, "total_cost_usd": 0.1575545},
    {"role": "no_group_replicate_1", "included": true, "run_dir": "runs/repeated_trust_game/1786420194", "event_log_sha256": "0ca52b16d920b529e37a490319f4281279c6d9c79ac56826b9c5ba9a9e155231", "resolved_config_sha256": "9a6fec32cc73848fc49b40d889e48a1be677dca7ca931838ba1d272dde7aa508", "completed": true, "total_cost_usd": 0.1252895},
    {"role": "no_commitment_group_replicate_2", "included": true, "run_dir": "runs/repeated_trust_game/1786420304", "event_log_sha256": "25cbf53c7248ef149c72f0b7afda36b037926000248e826477a119485a453341", "resolved_config_sha256": "99eb354e8f0d2b4f2ae45188b4166e995d2ed1c2c041f8657fe89ee19509c927", "completed": true, "total_cost_usd": 0.1218853},
    {"role": "covenant_replicate_2", "included": true, "run_dir": "runs/repeated_trust_game/1786420305", "event_log_sha256": "16bb9c845a4e89e198dcaba4df9530aac75a4ec0f3a04e3e5b16ad4b0772bbc9", "resolved_config_sha256": "d99350eae0f449022bf5321dd6d9f806933f33f907d6e61732a899b6b51832cb", "completed": true, "total_cost_usd": 0.1535512},
    {"role": "covenant_replicate_3", "included": true, "run_dir": "runs/repeated_trust_game/1786420306", "event_log_sha256": "d9696f9283513f6710495408a1001a64a7803dd9e2d4c2c0dc8b6d21f6c257e7", "resolved_config_sha256": "d99350eae0f449022bf5321dd6d9f806933f33f907d6e61732a899b6b51832cb", "completed": true, "total_cost_usd": 0.15199620000000003},
    {"role": "no_group_replicate_2", "included": true, "run_dir": "runs/repeated_trust_game/1786420307", "event_log_sha256": "a2a27fc2262f443c05b30b52c598b0468b325362d7c0a2effa2b3395977c1559", "resolved_config_sha256": "9a6fec32cc73848fc49b40d889e48a1be677dca7ca931838ba1d272dde7aa508", "completed": true, "total_cost_usd": 0.1226068},
    {"role": "no_commitment_group_replicate_3", "included": true, "run_dir": "runs/repeated_trust_game/1786420308", "event_log_sha256": "30660d0f2427fe754dc8779d051854dc6898b7478a93d5a193924fc8d8fcd938", "resolved_config_sha256": "99eb354e8f0d2b4f2ae45188b4166e995d2ed1c2c041f8657fe89ee19509c927", "completed": true, "total_cost_usd": 0.1232874},
    {"role": "no_group_replicate_3", "included": true, "run_dir": "runs/repeated_trust_game/1786420309", "event_log_sha256": "079f0c93e947ee350b141c07537498a7876e11ebd56901ac164201502d2e8c76", "resolved_config_sha256": "9a6fec32cc73848fc49b40d889e48a1be677dca7ca931838ba1d272dde7aa508", "completed": true, "total_cost_usd": 0.1218965}
  ]
}
-->

## Question

In a repeated LLM implementation of the standard trust-game schedule, does the
human covenant bundle increase trust (amount sent from 10) and reciprocity
(amount returned from a fixed 21) relative to the no-commitment group and
no-group controls?

## Expected decision

This is an instrument and fixed-seed variance pilot, not a model-general effect
claim. Each of the three human-parallel conditions is launched three times with
the same seed and Claude Sonnet 5, giving nine complete trajectories. The
replicates estimate stochastic model spread under fixed inputs; they do not
justify a normal approximation, statistical-significance claim, or
between-seed generalization.

| Preregistered observation | Decision triggered |
|---|---|
| Any included run lacks `simulation_ended`; any covenant run lacks two structured pledge events or logged 10% forfeitures; or a completed run has no decision from one role | Close as execution-invalid and repair the instrument before replacement runs. |
| Covenant exceeds the no-commitment group by at least 1.0/10 mean sent and 2.0/21 mean returned, with the same positive sign in all three replicate positions and usable variation | Open a fresh-seed replication record using the same three runs per arm. The no-group comparison remains secondary. |
| All three conditions share a practical trust floor (mean sent ≤0.5 and returned ≤1.0) or ceiling (mean sent ≥9.5 and returned ≥20.0) | Do not add unchanged replicas. Revise the instrument before testing treatment effects. |
| Any other result | Close as inconclusive and report per-run means and spread before deciding whether a revised design or a larger replication is useful. |

The primary comparison is covenant versus the human study's no-commitment
group. A pledge-only condition is deliberately excluded: it was not a primary
human-study arm and would be a later mechanism ablation only if this direct
comparison produces an informative contrast.

## Design

The instrument uses `repeated_trust_game`, a two-agent, 16-round hidden-horizon
scenario. The agents alternate roles: in each trustor decision an agent has a
10-unit endowment and chooses how much to send, from 0 to 10. In each trustee
decision the agent is told that a counterpart sent the standardized 7 units,
which is tripled to 21, and chooses how much to return, from 0 to 21.

The trustee input is intentionally fixed rather than a live transfer from the
other LLM. That matches the human study's controlled 7→21 reciprocity decision
and prevents different receipts from confounding the condition contrast. This
is therefore a repeated human-parallel decision probe, not a live bilateral
exchange or a test of a full covenant equilibrium. Participants have no
messaging tool.

| Fixed factor | Value |
|---|---|
| Model / provider | `claude-sonnet-5` / Anthropic |
| Seed | 61 |
| Replicates | 3 independent trajectories per condition, 9 total |
| Rounds / horizon | 16 / undisclosed |
| Participants | 2, alternating trustor and trustee roles |
| Trustor decision | send 0–10 from a 10-unit endowment |
| Trustee decision | return 0–21 after a fixed 7-unit send is tripled to 21 |
| Communication | none |

| Condition | Public group | Fairness pledge | Forfeiture |
|---|---:|---:|---:|
| No group | no | no | 0% |
| No-commitment group | yes | no | 0% |
| Covenant | yes | yes | 10% of retained game earnings |

Forfeiture is a covenant membership cost, not a violation-contingent sanction:
it is automatically deducted from retained earnings on every decision. It
should not be interpreted as a fine, a reward for trust, or an extra operating
benefit. Conditions differ only in group framing, pledge exposure, and the
human-study 10% forfeiture.

## Outcomes inspected

Primary, per completed run:

- trust: mean amount sent and its distribution, on a 0–10 scale;
- reciprocity: mean amount returned and its distribution, on a 0–21 scale;
- covenant minus no-commitment-group paired differences by replica position.

Secondary, reported separately:

- pledge affirmation or decline;
- decision completion by participant and role;
- gross retained earnings, forfeiture paid, and net balance;
- tool-call count, runtime, token use, and API cost.

The experiment does not measure deception, inspection effort, correctness,
repair, sanctions, financial insurance, stable equilibrium, or transmission to
newcomers. It must not be used to make claims about them.

## Provenance

- Base commit at planning: `d542f42d78f952601349c2106c7b8bf2466ed755`.
- Worktree dirty at planning: `true`, due the untracked `.claude/worktrees/`
  directory and this record bundle. The scenario implementation and tests are
  committed at the recorded SHA.
- Exact commands and immutable configuration hashes are in the
  machine-readable block. Each command will run exactly three times, with no
  fork, resume, source run, or replacement.
- The closing record will derive all reported numbers from
  `repeated_trust_*` events in the included JSONL logs and will record each
  log and resolved-config hash.

## Result

All nine planned trajectories ended with an authoritative
`simulation_ended` event after 16 completed rounds. Each run contained 16
trustor and 16 trustee decisions across the alternating participants. The six
covenant participants all affirmed the structured pledge, and the covenant
arms recorded **66.4 units** of automatic forfeiture; no other arm recorded a
pledge event or forfeiture.

The covenant arm increased the trustor decision relative to the primary
no-commitment-group comparator in all three replica positions: the condition
means were **7.17/10** sent in covenant (sample SD 0.29) versus **6.00/10** in
the no-commitment group (SD 0.00), a +1.17 difference. The no-group mean was
5.50/10 (SD 0.50). However, the trustee outcome was invariant: every one of
the 144 completed trustee decisions returned **10/21**. Covenant, group, and
no-group therefore all had a mean reciprocity of 10.00/21.

The planned batch cost **$1.2122**. Every result above is derived from the nine
event logs by [`analysis/summarize_runs.py`](analysis/summarize_runs.py), whose
checked output is [`analysis/results.json`](analysis/results.json).

## Outcome

**Inconclusive.** The trust component met its directional threshold: covenant
exceeded the no-commitment group by at least one unit in each replica position.
But the preregistered decision required both a trust and a 2-unit reciprocity
contrast. Reciprocity showed no condition variation, so the gate did not pass
and a fresh-seed replication is not authorized. This is not a practical floor
or ceiling under the stated rule, but it is a fixed-response limitation for
the reciprocity outcome.

## Validity limitations

- The 10% forfeiture is mechanically deducted per decision rather than once
  after the study, although it has the same proportional form as the human
  condition.
- Repeated interaction changes the human study's one-shot setting. It is added
  to observe persistence, but makes this an extension rather than an exact
  behavioral replication.
- Fixed trustee input ensures comparability but intentionally removes actual
  within-pair transfer dependence.
- The covenant condition is a human-parallel bundle; this record cannot
  attribute an effect to the pledge versus forfeiture.
- The scenario captures commitment framing and cost, not the full institutional
  covenant mechanism of durable membership, boundary enforcement, or shared
  governance.
- All trustee decisions returned 10/21. This prevents the current instrument
  from resolving a treatment effect on reciprocity, even though its numerical
  scale is neither at the preregistered floor nor ceiling.
- The three same-seed trajectories measure only conditional LLM sampling
  variation. They do not establish a between-seed effect or generalize to
  another model.

## What it changed

The scenario successfully implemented the three human-study conditions as
distinct, event-verifiable treatments and produced an interpretable trust
contrast under repeated interaction. It also showed that the unchanged
trustee framing elicits a rigid 10/21 policy from Sonnet. The next step is a
small, separately preregistered instrument revision that preserves the fixed
7→21 input while creating a genuine reason for trustees to vary their return;
it should not be another unchanged seed batch.

## Traps found

- Do not call fixed 7→21 a live exchange: it is a controlled trustee input.
- Do not treat sixteen rounds in one trajectory as sixteen independent samples.
- Do not interpret the forfeiture as a violation penalty or as a mechanism that
  makes trusting individually profitable.
- A non-floor, non-ceiling numerical average can still be uninformative when
  every model decision repeats the same value.
