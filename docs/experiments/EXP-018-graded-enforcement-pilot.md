# EXP-018 — Graded enforcement after an experienced failure

**Status:** planned
**Date opened:** 2026-08-05
**Date closed:** —

<!-- experiment-record:v1
{
  "schema_version": 1,
  "experiment_id": "EXP-018",
  "base_commit": "48cacef2e81489c165efff643e688cf7ffd96270",
  "worktree_dirty": true,
  "commands": [
    "PYTHONPATH=. .venv/bin/python -m glossogen resume-at-round bonded_team_production --source-run-dir ./runs/bonded_team_production/1785884603 --round-start 19 --rounds-after-resume 5 --runs-dir ./runs --knobs src/glossogen/scenarios/bonded_team_production/knobs_graded_enforcement_override.json"
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
      "role": "strict_control",
      "included": true,
      "run_dir": "runs/bonded_team_production/1785884603",
      "event_log_sha256": "f9c522949c0f3f732794d0cdf28644257633102a15925eb2940e2ff8ff7aac37",
      "resolved_config_sha256": "3f2ef1e22a5b4cfca7ecb4d4cac7eef934cd84e017443b4ce37d285ce1cb02d0",
      "completed": true,
      "total_cost_usd": 1.908807
    }
  ]
}
-->

## Question

After the same experienced and audited team failure, can first-offense
probation preserve the minimum viable three-member association long enough to
continue production, without hiding repeat non-compliance, compared with
immediate expulsion?

## Expected decision

- Treat the run as invalid unless case 18 resolves at the round-19 boundary
  with the same 125-unit bond refund and 30-unit fines for `provider_c` and
  accountable lead `provider_a`, while both remain active with one confirmed
  violation and public probation.
- Treat operational preservation as activated if the graded branch completes
  the first post-sanction order and at least three of rounds 19–24. If fewer
  than three orders complete, do not spend on replications of this policy.
- If at least three orders complete, replicate the shared-prefix comparison
  before interpreting recurrence, effort, accuracy, or repair as a policy
  effect. Replicate whether the first trajectory looks favorable or
  unfavorable.
- Do not combine operational continuity and alignment into one success score.
  Report hidden effort, correctness, truthful attestations, payment, repeat
  sanctions, membership, and bond solvency separately.
- Do not extend this pilot beyond round 24. Any repeated-failure or longer-run
  test becomes a separately recorded experiment.

## Design

The strict control is the completed EXP-017 trajectory
`runs/bonded_team_production/1785884603`. It reached round 18 with exactly three
active members. `provider_c` deliberately reused a stale record, disclosed that
it had not inspected, and submitted an incorrect count. `provider_a` was the
accountable lead. The scheduled round-19 audit refunded the client, fined both
providers, expelled both immediately, and left one member, so rounds 19–24
could not be staffed.

The graded branch resumes that same run at the start of round 19. Rounds 1–18,
including the agents' histories, the natural effort omission, the incorrect
delivery, payment, truthful attestation, unresolved audit, balances, membership,
and 135-unit bond, are inherited verbatim. Round 19 and later are replayed.
Only `expulsion_violation_threshold` changes from `1` to `2`: the first
confirmed violation still triggers the same refund and individual fines, but
the implicated members remain active under probation. A second confirmed
violation triggers permanent expulsion.

Both branches use GPT-5.5 through OpenAI, seed 46, six configured providers,
three-person orders, the hidden horizon, identical round-19–24 cases and audit
schedule, and the same economic profiles. Only three providers remain active
at the fork. The independent replication unit is a resumed trajectory, not a
round.

## Outcomes inspected

- activation parity: case, refund due and paid, bond drawdown, fine per
  implicated provider, probation, expulsion, and active membership;
- completion and correctness for each of rounds 19–24;
- inspected assignments separately from delivered accuracy;
- attestation truthfulness and disclosed concerns;
- promised and transferred payments;
- repair action, statement, and material contribution;
- repeat audit failures, violation counts, sanctions, and expulsions;
- voluntary exits, inability to staff, ending active membership, and bond
  balance.

Numbers will be selected from authoritative `team_production_*` JSONL events.
`team_production_order_settled` supplies completion, correctness, inspection,
payment, and bond measures. Audit, sanction, attestation, repair, and membership
events supply the corresponding behavioral and enforcement measures. Rounds
19–24 are the post-sanction observation window.

## Provenance

- Base implementation commit: `48cacef2e81489c165efff643e688cf7ffd96270`
- Branch: `feat/bonded-counter-association-impl`
- Strict source/control: `runs/bonded_team_production/1785884603`
- Fork boundary: start of round 19; rounds 1–18 are preserved and round 19 is
  replayed.
- Model/provider: `gpt-5.5` / `openai`, inherited and pinned for every provider.
- Seed: `46`
- Configured horizon: round 24; six post-sanction rounds, 19–24.
- Override:
  `src/glossogen/scenarios/bonded_team_production/knobs_graded_enforcement_override.json`
- Exact command: recorded in the machine-readable block above.
- Planning was marked dirty because the experiment record and override were
  created after the implementation commit and `.claude/worktrees/` is an
  unrelated untracked directory. The implementation itself is fully captured
  by the base commit; the record and override will be committed before launch.

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
