# EXP-052 — Completing the Sonnet 5 ladder: the missing `rule` arm

**Status:** planned
**Date opened:** 2026-08-19
**Date closed:** —
**Research program:** covenant-game
**Study:** STUDY-015 — Informational versus dispositional failure at the frontier
**Role:** replication

<!-- experiment-record:v2
{
  "base_commit": "0c2f6a7255a34783b5007d99539f022ec179cb72",
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run repo_stewardship --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-052-sonnet-rule-arm/configs/rule-resolved.json"
  ],
  "configs": [
    {
      "launch_path": "docs/research/covenant-game/experiments/EXP-052-sonnet-rule-arm/configs/rule-resolved.json",
      "path": "docs/research/covenant-game/experiments/EXP-052-sonnet-rule-arm/configs/rule-resolved.json",
      "sha256": "699416525e7d2b922cff88dcd83a86c0f5164f6d21a3e68adaa6d5cc2c889579"
    }
  ],
  "experiment_id": "EXP-052",
  "experiment_role": "replication",
  "research_program": "covenant-game",
  "runs": [],
  "schema_version": 2,
  "study_id": "STUDY-015",
  "worktree_dirty": true
}
-->

## Question

`claude-sonnet-5` has a `baseline` arm (n=15) and a `covenant` arm (n=15) on this
instrument and **no `rule` arm**. It is therefore the one model family of four
where governance can be shown to work but cannot be attributed: the covenant arm
carries both a stated obligation and an affirmation, and without the
neutral-language twin there is no way to tell which did the work.

Per [covenant-definition.md](../../covenant-definition.md), any arm carrying a
stated obligation requires a materially equivalent, neutral-language control
before anything is attributed to the covenantal framing. This experiment supplies
that control.

Two questions, in order of importance:

1. Does `claude-sonnet-5` reproduce the flat `rule` ≈ `covenant` result seen in
   every other family?
2. Does the governance effect on Sonnet (baseline 1.67 → covenant 0.87) survive
   when the treatment is an imposed rule rather than an affirmed commitment?

## Expected decision

Measured on `critical_defects_remaining`, the endpoint used for the cross-model
comparison, reported with within-arm range.

- **`rule` lands near `covenant` (both well below baseline)** → the Sonnet ladder
  matches the other three families. The four-family governance result becomes
  attributable to the stated obligation rather than to affirmation, and the
  cross-model table can be published with a complete ladder in four of five
  families.
- **`rule` lands near `baseline`, with `covenant` below both** → affirmation is
  carrying the effect on this model. This would be the **first** separation of
  covenant from rule in the program's history and would immediately become the
  most important open result. It would require direct replication before any
  claim.
- **`rule` lands below `covenant`** → the imposed rule outperforms the affirmed
  one, consistent in direction with the retired disclosure-substitution pattern.
  Report descriptively; do not build on a single cell.

**Preregistered prediction.** `rule` ≈ `covenant`, both well below baseline,
matching Haiku, GPT, and Kimi. Stated so a separation, if it appears, cannot be
narrated afterwards as expected.

**Stopping rule.** Fifteen simulations, matching the existing arms' n, launched
together, all scored. No interim look, no extension, no re-specification after
seeing values. A run that does not emit `simulation_ended` is excluded and
replaced by one relaunch; more than three such failures aborts the experiment.

**Zero-activity runs.** Same criterion as EXP-051: a run in which neither agent
invokes a budget-consuming action across all six ticket rounds is counted as
`idle_stall` and every table is reported with and without them.

## Design

**Instrument:** `repo_stewardship`, discoverable disclosure mode, judge oracle,
live reviewer, decision-point retrieval on (as in every governed arm).

**Arm:** `rule` only. The `baseline` (n=15) and `covenant` (n=15) arms already
exist on disk from the earlier Sonnet batch; this experiment adds the missing
third arm rather than re-running the other two.

**Config identity is verified, not assumed.** The existing Sonnet `covenant` runs
were diffed key-by-key against EXP-048's `rule-resolved.json`. Every key matches
except `condition` itself. The bundled config is therefore the exact
neutral-language twin of the Sonnet covenant arm, and carries the same SHA-256
(`699416525…c889579`) used by EXP-048, EXP-050, and EXP-051.

**One known asymmetry against the existing arms.** The earlier Sonnet runs predate
EXP-049's `board_item_action_cost` and `tracker_noise_enabled` knobs, so their
resolved configs lack those keys entirely, while these runs will carry them at
their inert defaults (`0` / `false`). EXP-050 established this is behaviourally
inert: its `rule` arm split five runs either side of the live `world.py` edit that
introduced the knobs and produced identical results (criticals 0.00 / 0.00,
repairs 2.00 / 2.00, incidental discoveries 0.80 / 0.80). The asymmetry is
recorded rather than assumed away, and is the one thing that would need checking
if this arm produces a surprise.

**Replication unit:** one simulation. Fifteen simulations. Rounds within a run are
not independent.

**Model/provider:** `claude-sonnet-5` via `anthropic` for both agents; judge
`claude-haiku-4-5-20251001` via `anthropic`. Seed 42.

**Budget.** `claude-sonnet-5` is $2.00/$10.00 per Mtok. At the observed trajectory
lengths on this instrument this projects to well under $1 per run, or roughly $10
for fifteen. Abandoned rather than extended if it exceeds $40.

## Outcomes inspected

Scored by EXP-048's
[`frontier_ceiling.py`](../EXP-048-frontier-ceiling-repo-stewardship/analysis/frontier_ceiling.py),
unmodified, so this arm is commensurable with every other cell in the cross-model
table.

**Primary.** `critical_defects_remaining`, compared against the existing Sonnet
`baseline` (1.67) and `covenant` (0.87) arms.

**Secondary, descriptive.** `developer_releases`, `reviewer_releases`,
`joint_breaches`, `repairs`, `disclosures`, `false_approvals`, plus the seven
throughput and review-quality outcomes.

**Instrument check.** `critical_defects_remaining == 2 − repairs`, which held in
30/30 EXP-050 runs and 29/30 EXP-051 runs. Any violation is diagnosed before the
result is interpreted.

**Analysis rule fixed in advance.** No outcome is added, dropped, or redefined
after values are seen. Only `critical_defects_remaining` decides anything.

## Provenance

- Base commit: `0c2f6a7255a34783b5007d99539f022ec179cb72`
- Worktree dirty at planning: `true`. Provisional and not code-replicable;
  artifact-verifiable via JSONL and resolved-config hashes.
- Exact command: see the machine-readable block. Launched from this bundle's
  `configs/`.
- Model/provider: `anthropic:claude-sonnet-5`
- Seed: 42
- Rounds: 7 configured (1 setup + 6 tickets)
- Source/fork boundary: none. Fifteen fresh runs.
- Comparison cells: the existing Sonnet `baseline` and `covenant` runs
  (`1787092473`–`1787093473`), which have one distinct resolved config each.

## Result

Pending.

## Outcome

Pending.

## Validity limitations

- **Non-concurrent control.** The comparison arms were run earlier, not
  interleaved with this one. Any drift in the instrument or the provider between
  the two dates is confounded with the arm. The inert-knob check above bounds the
  known instrument change; provider-side drift is not observable from here.
- **Fifteen runs.** Sufficient to place `rule` relative to two arms of the same n.
  Not sufficient to bound a small rule-versus-covenant difference; a separation
  would require direct replication before any claim.
- **Single endpoint decides.** Secondary outcomes are descriptive.
- **Not a covenant result** unless `rule` and `covenant` separate, which has not
  happened in any family and is not predicted here.
- **One configuration.** Discoverable disclosure, judge oracle, 14-action budget,
  seed 42.

## What it changed

Pending.

## Traps found

Pending.
