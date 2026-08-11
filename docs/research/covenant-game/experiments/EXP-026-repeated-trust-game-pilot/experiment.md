# EXP-026 — Repeated trust-game human-parallel pilot

**Status:** planned
**Date opened:** 2026-08-11
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
  "runs": []
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

Pending execution.

## Outcome

Pending preregistered decision gate.

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

## What it changed

Pending execution.

## Traps found

- Do not call fixed 7→21 a live exchange: it is a controlled trustee input.
- Do not treat sixteen rounds in one trajectory as sixteen independent samples.
- Do not interpret the forfeiture as a violation penalty or as a mechanism that
  makes trusting individually profitable.
