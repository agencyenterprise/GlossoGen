# EXP-020 — Cross-model compatibility pass

**Status:** running
**Date opened:** 2026-08-05
**Date closed:** —

<!-- experiment-record:v1
{
  "schema_version": 1,
  "experiment_id": "EXP-020",
  "base_commit": "dba81e87b0cc3eae953afc8a872f6baaff82b2ca",
  "worktree_dirty": true,
  "commands": [
    "PYTHONPATH=. .venv/bin/python -m glossogen run bonded_team_production --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/experiments/EXP-020-cross-model-compatibility/configs/independent.json",
    "PYTHONPATH=. .venv/bin/python -m glossogen run bonded_team_production --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/experiments/EXP-020-cross-model-compatibility/configs/covenant.json",
    "PYTHONPATH=. .venv/bin/python -m glossogen run bonded_team_production --model claude-opus-5 --provider anthropic --runs-dir ./runs --config docs/experiments/EXP-020-cross-model-compatibility/configs/independent.json",
    "PYTHONPATH=. .venv/bin/python -m glossogen run bonded_team_production --model claude-opus-5 --provider anthropic --runs-dir ./runs --config docs/experiments/EXP-020-cross-model-compatibility/configs/covenant.json",
    "PYTHONPATH=. .venv/bin/python -m glossogen run bonded_team_production --model gpt-5.6-terra --provider openai --runs-dir ./runs --config docs/experiments/EXP-020-cross-model-compatibility/configs/independent.json",
    "PYTHONPATH=. .venv/bin/python -m glossogen run bonded_team_production --model gpt-5.6-terra --provider openai --runs-dir ./runs --config docs/experiments/EXP-020-cross-model-compatibility/configs/covenant.json",
    "PYTHONPATH=. .venv/bin/python -m glossogen run bonded_team_production --model gpt-5.6-sol --provider openai --runs-dir ./runs --config docs/experiments/EXP-020-cross-model-compatibility/configs/independent.json",
    "PYTHONPATH=. .venv/bin/python -m glossogen run bonded_team_production --model gpt-5.6-sol --provider openai --runs-dir ./runs --config docs/experiments/EXP-020-cross-model-compatibility/configs/covenant.json"
  ],
  "configs": [
    {
      "path": "docs/experiments/EXP-020-cross-model-compatibility/configs/independent.json",
      "sha256": "807a00c5139fee2115a889d5b221694005fe2bc29250b53fa1df12b06edc9918"
    },
    {
      "path": "docs/experiments/EXP-020-cross-model-compatibility/configs/covenant.json",
      "sha256": "39fb83efa616490e612762200951100fbb2c0a133d07921f2162fce7901ce877"
    }
  ],
  "runs": [
    {
      "role": "sonnet_5_covenant",
      "included": true,
      "run_dir": "runs/bonded_team_production/1785958415",
      "event_log_sha256": "ee7d4c1b4cc7e743c0e3914cd9c63e5c33f6fb460d16868fbd03ed0534d0230d",
      "resolved_config_sha256": "77c78a95fd40e8f6a5c797eb8f105f5830581161b42e5b2bff1a66b9b0604d7b",
      "completed": true,
      "total_cost_usd": 2.5159098
    },
    {
      "role": "sonnet_5_independent",
      "included": true,
      "run_dir": "runs/bonded_team_production/1785958416",
      "event_log_sha256": "3856633b09c65f678d04eebd0459ec41461a530dcdbcc1cb53e7243ca3bb0975",
      "resolved_config_sha256": "d5b9d5a280bf220dd5f972edf9f7fd0b48361964ae69c691392d0612bd195ff1",
      "completed": true,
      "total_cost_usd": 3.8264985
    }
  ]
}
-->

## Question

Can Claude Sonnet 5, Claude Opus 5, GPT-5.6 Terra, and GPT-5.6 Sol each
complete the frozen fifteen-round independent-market and covenant conditions
without model-specific execution or instrumentation failure?

## Expected decision

- Run one fresh matched pair for every model regardless of behavioral outcome.
- A run passes compatibility only if it ends with `simulation_ended`, registers
  all six providers under the requested model/provider, advances all fifteen
  configured rounds, and produces authoritative team-production outcome events
  that can be analyzed with the same rules as the GPT-5.5 reference.
- A model passes the compatibility gate only if both its independent and
  covenant arms pass. Operational collapse caused by agent choices remains a
  valid behavioral result; malformed tool use, provider errors, missing events,
  or timeouts that prevent measurement are compatibility failures.
- Do not tune economics or prompts separately for any model in response to its
  behavior. Diagnose interface failures only, and preregister any rerun.
- If all models pass, use these trajectories to estimate run-level variance and
  preregister a fixed-size paired-seed confirmatory grid. Do not treat this
  one-pair pass as evidence of a model-general treatment effect.

## Design

Each model receives two fresh fifteen-round trajectories at seed 45. The
independent arm has no institution, visible membership, shared bond, or
expulsion. The treatment arm starts all six providers as public covenant
members, gives the association premium contracts and a shared refund bond, and
enables permanent expulsion after a confirmed violation.

Within every model, the two arms have identical providers, team size, case
sequence, economic profiles, audit and attestation schedules, hidden horizon,
channel affordances, starting balances, liability, and task mechanics. Across
models, both bundled configuration files remain byte-identical; only the model
and provider CLI arguments change. The existing GPT-5.5 seed-45 pair from
EXP-012 is the reference trajectory and is not rerun or counted as a new
replica.

The independent unit is one full multi-agent trajectory. Rounds are repeated
measurements within a run, not independent observations. These eight runs are a
compatibility and variance-estimation pass; causal and cross-model conclusions
require the later paired-seed grid.

## Outcomes inspected

Compatibility gates:

- completion marker, registered models/providers, configured and advanced
  rounds, malformed/failed tool calls, timeouts, and required event coverage;
- completed orders and whether any absence of later orders is a valid
  institutional outcome or an instrumentation failure.

Descriptive behavioral measures, without confirmatory claims:

- assigned zones inspected, stratified by effort-favorable, marginal, and
  shirking-tempting profiles;
- completed and correct orders, kept-stale outcomes, and client losses;
- truthful and false effort attestations;
- promised and transferred teammate payments;
- audits, refunds, sanctions, repair actions, exits, active membership, and
  bond balance;
- run-level covenant-minus-independent differences within each model.

## Provenance

- Base commit: `dba81e87b0cc3eae953afc8a872f6baaff82b2ca`
- Branch: `feat/bonded-counter-association-impl`
- Worktree dirty at planning: `true` only because of the unrelated untracked
  `.claude/worktrees/` directory; all experiment code and bundled configs are
  committed.
- Scenario: `bonded_team_production`
- Models/providers: `claude-sonnet-5` / Anthropic, `claude-opus-5` /
  Anthropic, `gpt-5.6-terra` / OpenAI, and `gpt-5.6-sol` / OpenAI.
- Seed: `45`
- Rounds: `15`, with the terminal horizon undisclosed to agents.
- Config ancestry: EXP-012's frozen seed-45 stability pair. The authoritative
  launch inputs are the two files in this bundle's `configs/` directory.
- Exact commands and config hashes are recorded in the machine-readable block.
- The initial preflight on 2026-08-05 exited before creating a run or making an
  API call because the planned commands used the obsolete `--knobs` flag. The
  commands were corrected to the current `--config` flag before any behavioral
  result was observed, and planned validation now rejects this mismatch.
- Completed Sonnet 5 covenant run:
  `runs/bonded_team_production/1785958415`.
- Completed Sonnet 5 independent run:
  `runs/bonded_team_production/1785958416`.
- Opus 5, GPT-5.6 Terra, and GPT-5.6 Sol runs have not yet launched.

## Result

Pending.

## Outcome

Pending.

## Validity limitations

Pending. This pass is intentionally one paired trajectory per new model and
cannot establish model-level repeatability or a general treatment effect.

## What it changed

Pending.

## Traps found

Pending.
