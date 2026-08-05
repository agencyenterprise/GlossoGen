# EXP-019 — Graded-enforcement shared-prefix replication

**Status:** planned
**Date opened:** 2026-08-05
**Date closed:** —

<!-- experiment-record:v1
{
  "schema_version": 1,
  "experiment_id": "EXP-019",
  "base_commit": "ae48c2bb1549f62822bf2005c0fe90df13ce48e8",
  "worktree_dirty": true,
  "commands": [
    "for replica in 1 2; do PYTHONPATH=. .venv/bin/python -m glossogen resume-at-round bonded_team_production --source-run-dir ./runs/bonded_team_production/1785884603 --round-start 19 --rounds-after-resume 5 --runs-dir ./runs --knobs src/glossogen/scenarios/bonded_team_production/knobs_graded_enforcement_override.json; done"
  ],
  "configs": [
    {
      "path": "runs/bonded_team_production/1785884603/replace_config.json",
      "sha256": "3f2ef1e22a5b4cfca7ecb4d4cac7eef934cd84e017443b4ce37d285ce1cb02d0"
    },
    {
      "path": "src/glossogen/scenarios/bonded_team_production/knobs_graded_enforcement_override.json",
      "sha256": "e8fef0ba6fc84956cd1c7325c746145cf3d0a7d9c57fe888cff29a039e07b996"
    }
  ],
  "runs": [
    {
      "role": "strict_source",
      "included": true,
      "run_dir": "runs/bonded_team_production/1785884603",
      "event_log_sha256": "f9c522949c0f3f732794d0cdf28644257633102a15925eb2940e2ff8ff7aac37",
      "resolved_config_sha256": "3f2ef1e22a5b4cfca7ecb4d4cac7eef934cd84e017443b4ce37d285ce1cb02d0",
      "completed": true,
      "total_cost_usd": 1.908807
    },
    {
      "role": "graded_pilot",
      "included": true,
      "run_dir": "runs/bonded_team_production/1785955619",
      "event_log_sha256": "08f7b1b034a219fb59f3b872477fd9f4f3bac4d2ae6b6d4343ce023b0d571fef",
      "resolved_config_sha256": "63080779e89b0501fbd83b4c7411c54422378f6c74a56bdb2026935e1d5feb1d",
      "completed": true,
      "total_cost_usd": 5.028054
    }
  ]
}
-->

## Question

Does the graded-enforcement result from EXP-018 repeat in two additional
GPT-5.5 trajectories that share the exact same history and confirmed failure
through round 18?

## Expected decision

- Require both replicas to activate the same round-19 enforcement: 125 refunded
  from the bond, 30-unit fines for `provider_c` and `provider_a`, one violation
  recorded for each, probation for both, no expulsion, and three active members.
  A failed activation makes that replica invalid.
- Call operational preservation replicated only if both new trajectories
  complete their first post-sanction order and at least five of six orders
  through round 24.
- Call the pilot's immediate-compliance pattern replicated only if each new
  trajectory records at least 15 of 18 inspections, no false attestation, and
  no second confirmed violation or expulsion. Report correctness separately
  because stale counts can be correct without effort.
- If both operational and immediate-compliance patterns replicate, move next to
  a fair strict-versus-graded comparison with enough reserve members that both
  policies can continue operating after the same sanction.
- If capacity replicates but effort or recurrence is mixed, prioritize a
  longer recurrence and replacement test before another enforcement-policy
  comparison.
- Do not extend either replica beyond round 24 or change the audit schedule.

## Design

Launch two independent `resume-at-round` runs from the EXP-017 strict trajectory
`1785884603` at the start of round 19. Both inherit rounds 1–18 verbatim,
including the three-member roster, balances, 135-unit bond, `provider_c`'s
experienced effort omission and truthful attestation, the incorrect case-18
delivery led by `provider_a`, and its unresolved audit.

Both use `expulsion_violation_threshold: 2`. The first confirmed violation
therefore retains both implicated members under probation; a second violation
expels them. GPT-5.5/OpenAI, seed 46, cases, economics, agent histories, hidden
horizon, audit and attestation schedules, team size, and rounds 19–24 are held
constant. Model stochasticity after the shared boundary supplies the only
between-replica behavioral variation.

The independent unit is a resumed trajectory. EXP-018 is reported as prior
pilot evidence, not counted as one of the two preregistered replication runs.

## Outcomes inspected

- enforcement activation, refund, fines, violation counts, probation, and
  expulsion;
- run-level completion, correctness, and inspections over rounds 19–24;
- attestation truthfulness and concerns;
- promised versus transferred payments;
- explicit repair actions and contributions;
- post-probation audits, repeat sanctions, exits, active membership, and bond;
- agreement or divergence across the two new trajectories and EXP-018.

All counts come from authoritative `team_production_*` JSONL events. Rounds are
not treated as independent replications.

## Provenance

- Base commit: `ae48c2bb1549f62822bf2005c0fe90df13ce48e8`
- Branch: `feat/bonded-counter-association-impl`
- Shared source: `runs/bonded_team_production/1785884603`
- Prior pilot: `runs/bonded_team_production/1785955619`
- Fork boundary: start of round 19; rounds 1–18 preserved, round 19 replayed.
- Model/provider: `gpt-5.5` / `openai`
- Seed: `46`
- Observation window: rounds 19–24
- Override:
  `src/glossogen/scenarios/bonded_team_production/knobs_graded_enforcement_override.json`
- Exact two-launch command: recorded in the machine-readable block.
- The dirty marker is conservative and reflects this planning record plus the
  unrelated untracked `.claude/worktrees/` directory. The scenario code and
  prior result are committed.

## Result

Pending.

## Outcome

Pending.

## Validity limitations

Pending.

## What it changed

Pending.

## Traps found

Pending.
