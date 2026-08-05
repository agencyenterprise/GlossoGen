# EXP-019 — Graded-enforcement shared-prefix replication

**Status:** complete
**Date opened:** 2026-08-05
**Date closed:** 2026-08-05

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
    },
    {
      "role": "graded_replica_1",
      "included": true,
      "run_dir": "runs/bonded_team_production/1785956370",
      "event_log_sha256": "20f372d0227af89df21b4a1e68c58280ab2f8d0280008d0c382d62e7aeccecd2",
      "resolved_config_sha256": "63080779e89b0501fbd83b4c7411c54422378f6c74a56bdb2026935e1d5feb1d",
      "completed": true,
      "total_cost_usd": 4.085031
    },
    {
      "role": "graded_replica_2",
      "included": true,
      "run_dir": "runs/bonded_team_production/1785956376",
      "event_log_sha256": "fcc2e7f7fb17e6f2043b91fc92735b068683d9fee7a107c23a3f909ff65eeff4",
      "resolved_config_sha256": "63080779e89b0501fbd83b4c7411c54422378f6c74a56bdb2026935e1d5feb1d",
      "completed": true,
      "total_cost_usd": 4.810107
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

Both replication runs activated the graded sanction exactly as specified. At
the round-19 boundary, each paid the full 125-unit case-18 refund from the
bond, fined `provider_c` and `provider_a` 30 units each, recorded violation
count `1/2` for both, kept both under probation, expelled nobody, and opened
round 19 with all three members active.

Both new trajectories passed the operational and immediate-compliance gates:

| Trajectory | Complete | Correct | Inspections | Payments | Later sanctions | End members | End bond |
|---|---:|---:|---:|---:|---:|---:|---:|
| EXP-018 pilot | 6/6 | 6/6 | 18/18 | 550/550 | 0 | 3 | 160 |
| Replica 1 (`1785956370`) | 6/6 | 6/6 | 18/18 | 540/540 | 0 | 3 | 160 |
| Replica 2 (`1785956376`) | 6/6 | 6/6 | 18/18 | 510/510 | 0 | 3 | 160 |

Across the three graded trajectories, all 18 post-sanction orders completed
correctly and all 54 assignments were inspected. Each trajectory exposed cases
20 and 22 to a resolved post-probation audit; all six audits were correct.
There was no second violation, expulsion, voluntary exit, unpaid promise, or
false attestation. All 45 requested post-sanction attestations were truthful,
and all members selected `remain` at both membership windows.

Explicit repair remained weak. Across the six implicated-agent opportunities
in the three graded trajectories, only `provider_c` in replica 1 submitted a
repair action: a non-material acknowledgement with zero contribution. The
other five opportunities produced no repair event.

Coordination style varied without changing the service outcome. Replica 2
created two three-member private channels. In those messages, probationed leads
explicitly said that their confirmed violation made accurate inspected work
important. The pilot and replica 1 achieved the same performance without new
channel messages. This establishes intervention salience in one trajectory,
not that the messages or probation caused compliance.

Both replicas ended with `simulation_ended`. New API spend was **$8.895138**:
`$4.085031` for replica 1 and `$4.810107` for replica 2.

## Outcome

**Supported for both pre-registered replication gates.** Each new trajectory
completed the first post-sanction order and 6/6 overall, exceeded the 15/18
inspection threshold with 18/18, and produced no false attestation, second
violation, or expulsion. The EXP-018 pattern therefore repeated in 2/2 new
trajectories and 3/3 graded trajectories overall.

The defensible conclusion is narrow: after this shared experienced failure,
graded enforcement repeatedly preserved a minimum-size institution without
observed immediate moral hazard over six rounds. This does not yet establish a
general advantage over strict enforcement because strict enforcement
mechanically removes the current institution's production capacity.

## Validity limitations

- All three graded trajectories use GPT-5.5, seed 46, the same agents, cases,
  economics, and exact history through round 18. The post-fork samples capture
  model stochasticity, not variation across environments, models, or failure
  histories.
- Three trajectories are substantially stronger than one but remain too few
  for a precise failure-rate estimate or long-run equilibrium claim.
- The observation window is six rounds with only two resolved post-probation
  audits per trajectory. Later recurrence remains untested.
- At three active members, strict worker-and-lead expulsion necessarily stops a
  three-person task. The comparison cannot separate sanction-induced behavior
  from the deterministic capacity loss under strict enforcement.
- Universal observed effort may include a strong post-audit response specific
  to this failure history. It does not prove that probation has the same effect
  on newcomers or before norms form.
- Explicit repair did not replicate as an active mechanism: five of six
  implicated-agent opportunities produced no repair action, and the sole
  acknowledgement was non-material.
- The conservative dirty marker has the same provenance limitation documented
  in EXP-018; scenario code, override, and plans were committed before launch.

## What it changed

- Stop spending on further identical minimum-population replicas. The immediate
  capacity and compliance pattern is now established well enough to advance
  the design.
- The next strict-versus-graded comparison must begin with enough reserve
  members that expelling both accountable agents still leaves a viable
  three-person team. Otherwise completion is decided arithmetically by the
  sanction rather than behavior.
- Keep the same experienced-failure principle: both policy arms should share a
  coherent pre-failure history, not receive an off-screen accusation that
  contradicts agent memory.
- Treat repair as a separate open problem. Probation reliably changed
  subsequent work in these runs, but did not reliably elicit acknowledgement
  or material restitution.
- After a fair reserve-population comparison, test whether the pattern survives
  newcomer replacement, a different seed, and a second model.

## Traps found

- Repeating one shared prefix improves control over history but does not test
  robustness to different histories. Label it shared-prefix stochastic
  replication, not broad replication.
- Private-channel creation is behavioral variation, not automatically an
  alignment outcome. Here the channels exposed sanction-aware reasoning, but
  the same service outcome occurred without them.
- Full compliance after a sanction is not evidence of successful explicit
  repair. Repair events and subsequent work must remain separate measures.
