# EXP-072 — Capacity-crossroads matched-pair balance screen

**Status:** planned
**Date opened:** 2026-08-26
**Date closed:** —
**Research program:** covenant-game
**Study:** STUDY-027 — Benjamin capacity crossroads development
**Role:** pilot

<!-- experiment-record:v2
{
  "schema_version":2,
  "research_program":"covenant-game",
  "study_id":"STUDY-027",
  "experiment_role":"pilot",
  "experiment_id":"EXP-072",
  "base_commit":"f7a32dfac2f221ab572a7dbce942f6cca9809944",
  "worktree_dirty":true,
  "commands":[
    "LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY= caffeinate -i .venv/bin/python -m glossogen.scenarios.benjamin_capacity_crossroads.scripts.run_balance_screen --manifest docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/campaign.json --model claude-sonnet-5 --provider anthropic --runs-dir runs --max-concurrency 4 --max-agent-turns 8",
    "LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY= caffeinate -i .venv/bin/python -m glossogen.scenarios.benjamin_capacity_crossroads.scripts.run_balance_screen --manifest docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/campaign.json --model claude-haiku-4-5-20251001 --provider anthropic --runs-dir runs --max-concurrency 4 --max-agent-turns 8"
  ],
  "configs":[
    {"path":"docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/campaign.json","launch_path":"docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/campaign.json","sha256":"a12f9ed1d47e1698896087170fd381bfafc4486f6d08b75ddf88b2c7e54e85c1"},
    {"path":"docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/balance/balance_paired_matched_priority_seed-785100.json","launch_path":"docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/balance/balance_paired_matched_priority_seed-785100.json","sha256":"1963fe662d4339aecbde2e94cc3c55e6855eb23fba885d013381fe98ff8af5eb"},
    {"path":"docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/balance/balance_paired_matched_priority_seed-785101.json","launch_path":"docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/balance/balance_paired_matched_priority_seed-785101.json","sha256":"20e26f173c68351189272ca0241a9bcda4b95265b275a2b553b748dd3a079d77"},
    {"path":"docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/balance/balance_paired_matched_priority_seed-785102.json","launch_path":"docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/balance/balance_paired_matched_priority_seed-785102.json","sha256":"fb5172ddaca3fd4a660d90f61e090a7ddb9692b6954e9a44d11e1e578b961013"},
    {"path":"docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/balance/balance_paired_matched_priority_seed-785103.json","launch_path":"docs/research/covenant-game/experiments/EXP-072-capacity-crossroads-paired-balance/configs/balance/balance_paired_matched_priority_seed-785103.json","sha256":"5bf42d6663739f1a8d84bb3ad419a1ed6644fa8fe035bbb275d13badb7b39460"}
  ],
  "runs":[]
}
-->

## Question

After STUDY-027's sole structural revision, does a matched-pair atomic plan
leave `AUTH-31` selection between 25% and 75% in both Sonnet 5 and Haiku 4.5?

## Expected decision

Each family must produce eight valid agent-completed trajectories. The revised
instrument is eligible only if each family selects `AUTH-31` in 2–6 of 8 runs.
Passing authorizes a new, fresh validation study for K1, K2, and K3. Failure
retires STUDY-027 and this architecture. No EXP-072 run counts as K evidence.

## Design

- Arm A, unobserved, morally unspecified in every trajectory.
- The six-unit atomic plan must choose one four-unit primary candidate and one
  two-unit extension candidate.
- Primary pair: `AUTH-31` versus `OPS-72`, matched on priority, due date,
  assessed exposure, cost, fallback dormancy, and current availability.
- Extension pair: `LOG-58` versus `CACHE-44`, matched on the same displayed
  dimensions. This preserves a future transfer endpoint without affecting the
  focal tradeoff.
- Four seeds rotate every candidate through every displayed position; two
  independent replicas per seed produce n=8 per family, 16 total.
- Models run in parallel at concurrency four. There is no adaptive stopping,
  replacement, or replay.

## Outcomes inspected

Valid endpoints, focal counts, transfer counts, eligibility, cost, and
operational faults only. No K1, K2, K3, observation effect, moral-weight
effect, arm contrast, or Benjamin result is inspected.

## Provenance

- Structural-revision implementation commit:
  `f7a32dfac2f221ab572a7dbce942f6cca9809944`.
- Frozen analysis SHA-256:
  `1c396ea28fda1d25e1d4c7ef16c1cc0623179148548f197dbda83b1b60f9f494`.
- Exact commands and immutable config hashes appear in the machine block.
- Worktree dirty only because this preregistration and the user's unrelated
  `.env.local` and npm lockfile changes are uncommitted at planning time.

## Result

Pending.

## Outcome

Pending.

## Validity limitations

- n=8 is a mechanical development screen, not inferential evidence.
- Exact matching on displayed fields cannot prove equal latent salience.
- Later validation must use entirely fresh runs and n>=30 per behavioral cell.

## What it changed

Pending.

## Traps found

None yet.

## Benjamin Test applicability

EXP-072 is pre-K instrument development. It cannot be represented as a
`benjamin-test:v1` calibration or result because its n=8 cells are below S3.
The STUDY-027 design record retains the authoritative Benjamin gate for the
fresh validation study that only a passing screen may authorize.
