# EXP-044 — Four-arm ladder replication at claim 42 under the corrected prompt

**Status:** planned
**Date opened:** 2026-08-12
**Date closed:** —
**Research program:** covenant-game
**Study:** STUDY-012 — Contribution ladder under a non-disclosing prompt
**Role:** replication

<!-- experiment-record:v2
{
  "base_commit": "070a4949f3b805d66a9db4421ad2efb0a2a641f3",
  "commands": [
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/no-group-claim42.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/group-claim42.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/pledge-claim42.json",
    "VIRTUAL_ENV= uv run --no-sync python -m glossogen run shared_reserve_commitment --model claude-sonnet-5 --provider anthropic --runs-dir ./runs --config docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/costly-pledge-claim42.json"
  ],
  "configs": [
    {
      "path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/no-group-claim42.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/no-group-claim42.json",
      "sha256": "00316c6443acf3043d9166ee548a107a704671f46e37ad4447ff8d3e5824ba81"
    },
    {
      "path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/group-claim42.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/group-claim42.json",
      "sha256": "36ec11eb069c74e7d5f4c9458688f22274b34dfe85df9149a8fabb5c064afc08"
    },
    {
      "path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/pledge-claim42.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/pledge-claim42.json",
      "sha256": "9f014e28d694990daccd43fb74ed8af273dc38a383f1510f7a3d379dd6247a0e"
    },
    {
      "path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/costly-pledge-claim42.json",
      "launch_path": "docs/research/covenant-game/experiments/EXP-044-corrected-prompt-ladder-replication/configs/costly-pledge-claim42.json",
      "sha256": "0643fedb5ff00838ecfcb38fd488bc32d0e862bf3b9628ada754adb0265e7a6b"
    }
  ],
  "experiment_id": "EXP-044",
  "experiment_role": "replication",
  "research_program": "covenant-game",
  "runs": [],
  "schema_version": 2,
  "study_id": "STUDY-012",
  "worktree_dirty": true
}
-->

## Question

Under a system prompt that no longer discloses that conditions are being
compared, does the EXP-038/EXP-039 world produce provider defection, and does
the four-arm ladder reproduce the ordering that batch recorded?

## Expected decision

A defecting baseline restores the headroom every batch since EXP-040 has
lacked, and licenses the mechanisms the collaboration has asked for but that
this instrument has never carried: loss of membership, and probing why agents
cooperate. A baseline that stays at zero refutes prompt disclosure as the
explanation for the flatness and leaves model drift as the remaining candidate,
to be tested separately by re-running the original code.

## Design

The world is byte-for-byte the batch-1 world. The four bundled configs are
exact copies of the EXP-038 and EXP-039 launch inputs and carry identical
SHA-256 hashes, so the knobs are not merely equivalent but the same files: two
providers, 21-unit endowment, 21 units per active round, `contribute` (7 to the
reserve, keep 14) or `retain` (keep 21), 17 rounds with an undisclosed ending,
and deterministic 42-unit claims after rounds 7 and 12. The disclosure knobs
added in EXP-043 sit at their defaults — `ledger_visibility: full`,
`free_form_messages_enabled: true`, reserve balance and claim amount both
disclosed — which reproduces the batch-1 behaviour exactly.

Six independent trajectories per arm, against three in batch 1. The trajectory
is the unit; the sixteen decision rounds inside one are repeated interaction,
not sixteen observations.

| Condition | Exposure |
|---|---|
| `no_group` | none |
| `group` | a public registry lists both providers as Shared Service Group members |
| `pledge` | group plus a public affirm/decline of a commitment to contribute every round |
| `costly_pledge` | pledge plus a real one-time 2.1-unit deduction on affirming (10% of the round payment) |

### The one deliberate difference

Both prompt templates were rewritten in `070a494`. The rendered system prompt
for a given arm goes from 274 words to 177, every sentence is reworded, and one
sentence is deleted outright:

> The same hidden claim schedule is used in every condition.

That sentence told providers they were inside an experiment whose conditions
are being compared. A model that knows it is being compared across arms has
reason to behave consistently across arms, which is the exact null this program
recorded in EXP-040, EXP-041, EXP-042, and EXP-043. Removing it is the
motivated hypothesis this replication tests.

This is therefore **not** a test of model drift. The prompt change is a known,
intended difference from batch 1, declared here rather than discovered later.
Separating drift from prompt requires re-running the original templates at
commit `e393852`, which this record does not do.

### Reference values from batch 1

Per arm, 96 opportunities across three trajectories:

| Arm | contribute | retain | no_decision |
|---|---|---|---|
| `no_group` (EXP-038) | 84 | 12 | 0 |
| `group` (EXP-039) | 66 | 27 | 3 |
| `pledge` (EXP-039) | 95 | 0 | 1 |
| `costly_pledge` (EXP-039) | 95 | 0 | 1 |

Every batch since — EXP-040, EXP-041, EXP-042, EXP-043, 48 trajectories — has
recorded a combined three retentions, none of them in a `no_group` arm.

## Outcomes inspected

- **Defection (primary):** `retain` actions over decision opportunities per arm,
  and the count of trajectories carrying at least one retention.
- **Service continuity:** coverage of each claim and any termination.
- **Pledge uptake and cost exposure:** affirm/decline counts and 2.1-unit
  deductions actually recorded.
- **Missed decisions:** `no_decision` settlements, counted separately from
  retentions and never merged into them.
- **Coordination talk:** free-form messages on the shared record, qualitative
  only, since this arm re-enables them.

### Preregistered gates

1. **Gate A — baseline activation.** At least one `retain` in the `no_group`
   arm across its six trajectories.
2. **Gate B — ladder ordering.** Evaluated only if Gate A passes. Batch 1 is
   reproduced when trajectories-with-defection satisfy both `group ≥ no_group`
   and `pledge < group` and `costly_pledge < group`. Report the arm contrast
   only under this gate.
3. **Gate C — prompt hypothesis refuted.** If Gate A fails, record that
   correcting the prompt does not restore variance, that design disclosure is
   not the explanation for the ceiling, and that the batch-1 versus later-batch
   divergence remains unexplained by any manipulation attempted in EXP-041
   through EXP-044. The authorized next step then becomes the verbatim re-run at
   `e393852`, which isolates model drift.

Gates are not revised after results are seen. Gate C is a real outcome, not a
failure to be worked around.

## Provenance

- Base commit: `070a4949f3b805d66a9db4421ad2efb0a2a641f3`
- Worktree dirty at planning: `true`, but only from two untracked non-code
  artifacts predating this work (`.claude/worktrees/` and a stray file under
  `experiments/2026-06-19_veyru_channel_noise/`). `src/` is fully committed at
  the base commit, so the code that produces these runs is reproducible from it.
- Exact command: see `commands` in the machine-readable block
- Config: the four bundled `configs/*-claim42.json`, hashed above and identical
  to the EXP-038 and EXP-039 launch inputs
- Model/provider: `claude-sonnet-5` / `anthropic`
- Seed: 74 in every config, and inert — this scenario reads no seed and has no
  RNG. This is not a fresh-seed replication and no seed-sensitivity claim
  follows from it.
- Rounds: 17 configured; claims at rounds 7 and 12
- Source/fork boundary: none; these are fresh runs

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
