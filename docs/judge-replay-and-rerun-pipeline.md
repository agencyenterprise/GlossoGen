# Judge replay and rerun pipeline

When the stabilization judge prompt changes, every historical `veyru_stabilization_judged` event that the *old* judge produced is suspect: a verdict the old prompt accepted (`judge_match=true`) may now flip to false under the new prompt, retroactively invalidating the runs that depended on it.

The pipeline in this doc:

1. Re-judges every previously-accepted verdict under the new prompt.
2. Surfaces flip rates per run in the FE and streamlit via per-run JSON sidecars.
3. Builds a topologically-sorted re-run plan of every contaminated run + every derived run that descended from one.
4. Re-executes the plan in two layers (originals first, derived runs second).
5. Recovers timeouts, re-runs network-impacted casualties, and merges side-state.
6. Re-replays the judge against the cleaned cohort so the FE/streamlit show 0 damage.

Everything lives in `scripts/` and writes to `runs/_judge_replay/`, `runs/_superseded/`, and `runs/_failed_network_timeout/`.

## Artifact directories

| Directory | Purpose |
|---|---|
| `runs/_judge_replay/pair_cache.jsonl` | Cache of unique `(expected_actions, observer_action)` pairs re-judged under the new prompt. Incremental — restartable. |
| `runs/_judge_replay/flips_by_run.jsonl` | One row per run that has at least one flipped verdict. |
| `runs/_judge_replay/summary.json` | Top-level counts: pairs, runs touched, flips. |
| `runs/_judge_replay/rerun_plan.json` | Affected-set + topological layers + per-spec `cli_invocation`. |
| `runs/_judge_replay/rerun_state.json` | Per-spec status (`queued` / `launched` / `sim_ended` / `evaluated` / `archived` / `error` / `excluded`). |
| `runs/_judge_replay/rerun_18_state.json` | Side-state used by `rerun_18_parallel.py` to avoid racing on `rerun_state.json`. Merged back at the end. |
| `runs/_superseded/<scenario>/<old_id>/` | Where superseded runs land after a successful rerun. Each carries `superseded_by.json` pointing at its replacement. |
| `runs/_failed_network_timeout/<scenario>/<new_id>/` | Where the *bad* new runs go when their original re-run had network-induced round timeouts and got re-executed. Kept for audit. |

Each run dir also gets a `judge_replay.json` sidecar (see schema below).

## `judge_replay.json` sidecar schema

Written into every run dir that had at least one `veyru_stabilization_judged` event with `judge_match=true`. Read by `src/schmidt/server/runs/discovery.py:_read_judge_replay` and exposed as `RunSummary.judge_replay` (Pydantic model `JudgeReplaySummary` in `src/schmidt/server/runs/models.py`).

```json
{
  "judge_model": "claude-haiku-4-5-20251001",
  "generated_at": "2026-06-01T07:27:00.000000+00:00",
  "old_true_count": 20,
  "new_true_count": 16,
  "flipped_true_to_false": 4,
  "flips": [
    {
      "event_id": "<uuid>",
      "round_number": 7,
      "agent_id": "field_observer",
      "expected_actions": "...",
      "observer_action": "...",
      "old_match": true,
      "new_match": false,
      "new_explanation": "..."
    }
  ]
}
```

Runs with zero flips still get a sidecar — the FE uses the file's presence to distinguish "replayed clean" from "not yet replayed".

### FE / streamlit surfaces

- **Frontend list view** ([frontend/src/features/runs/run-list.tsx](frontend/src/features/runs/run-list.tsx)): renders an `AlertTriangle` badge on any row where `judge_replay.flipped_true_to_false > 0`. Hovering shows the flip rate.
- **Streamlit "Judge replay" tab** ([analysis/results_viewer/judge_replay_tab.py](analysis/results_viewer/judge_replay_tab.py)): per-primary-model bar chart of flip rate, with a table listing the worst-offender run per model.
- **Per-tab filter slider** ([analysis/results_viewer/judge_replay_filter.py](analysis/results_viewer/judge_replay_filter.py)): every analysis tab has a slider at the bottom that filters out runs above the chosen flip-rate threshold.

## End-to-end runbook

The whole pipeline assumes you're running from the repo root with `make install` already done. Each step is restartable.

### Step 1 — Re-judge previously-accepted verdicts

```bash
VIRTUAL_ENV= uv run --no-sync python scripts/replay_veyru_judge.py
```

Walks `runs/veyru/*/veyru.jsonl`, extracts unique `(expected_actions, observer_action)` pairs whose original `judge_match=true`, calls the updated stabilization judge on each *unique* pair (deduped + cached), writes the artifacts under `runs/_judge_replay/`. Concurrency 100. Resumable via `pair_cache.jsonl`.

### Step 2 — Write per-run sidecars

```bash
VIRTUAL_ENV= uv run --no-sync python scripts/write_judge_replay_sidecars.py
```

Reads the cache + flips JSONL, joins back to each run dir, writes `judge_replay.json` per run. The FE / streamlit / `RunSummary` start serving the data after this.

### Step 3 — Build the rerun plan

```bash
VIRTUAL_ENV= uv run --no-sync python scripts/build_rerun_plan.py --threshold 0.20
```

Threshold is the flip-rate cutoff for "contaminated" (default 0.20). Walks the run tree, identifies seed contaminated runs, propagates to every transitive descendant via `replace_manifest.json` / `cross_run_replace_manifest.json` / `AgentSwappedMidRun` chains, topologically sorts (parents before children), writes `rerun_plan.json` with one entry per spec carrying:

- `run_id`, `run_dir`, `kind` (`original` / `replace_agent` / `cross_run` / `resume_at_round`)
- `parents` (1 for replace_agent / resume_at_round; 2 for cross_run)
- `flip_rate`, `flip_rate_above_threshold`
- `primary_model`, `primary_provider`, `model_overrides`
- `scenario_config`
- `cli_invocation` — the fully-substituted command to re-execute, with `<NEW_SOURCE_RUN_DIR_FOR_<parent_run_id>>` placeholders for any parent that is itself in the rerun set

The plan ships with N topological layers. Layer 0 has no contaminated parents; each subsequent layer depends only on earlier layers.

### Step 4 — Run layer 0

```bash
nohup bash -c 'VIRTUAL_ENV= uv run --no-sync python scripts/run_rerun_plan.py --layer 0 \
  >> /tmp/layer0_orchestrator.log 2>&1' > /tmp/layer0_orchestrator.stdout 2>&1 &
disown
```

The orchestrator pipeline per spec: launch → wait-for-simulation-end → eval → write labels → archive. Concurrency is per-provider (`PER_PROVIDER_CONCURRENCY`, default 10) — anthropic and openai share independent semaphores so a paused provider can't block the other.

Key state transitions, persisted to `rerun_state.json` after every step:

- `queued` → `launched` (sim dir claimed, judge_replay.json cleaned)
- `launched` → `sim_ended` (simulation_ended event seen)
- `sim_ended` → `evaluated` (`schmidt evaluate` ran with the predecessor's metric set)
- `evaluated` → `archived` (predecessor moved to `_superseded/`, labels cloned + `supersedes:<old>` written)

Common per-spec flags worth knowing:

- `--only RUN_ID` — execute exactly one spec (for smoke / validation)
- `--exclude-model M` (repeatable) — defaults already drop `Qwen/Qwen3-32B` and `meta-llama/Llama-3.3-70B-Instruct`
- `--dry-run` — print substituted CLIs + per-provider counts without launching

### Step 5 — Recover sim_wait_timeout casualties

Long-round-count specs sometimes finish naturally after `SIM_WAIT_TIMEOUT_SEC` expires; the orchestrator marks them `error` but the sim itself emitted `simulation_ended` on disk.

```bash
VIRTUAL_ENV= uv run --no-sync python scripts/recover_errored_reruns.py
```

Walks every `error` entry, checks `simulation_ended` + `python_still_writing`, finishes the pipeline (eval → labels → archive) for the completed orphans. Skips the in-flight ones — rerun after they finish.

### Step 6 — Re-audit recovered runs for network-impacted timeouts

```bash
VIRTUAL_ENV= uv run --no-sync python scripts/rerun_network_impacted.py --dry-run
```

A run is "network-impacted" when it has `round_ended_timeout > 0` AND its debug log contains `ERROR`-level or network-keyword `WARNING`-level entries (`retry`, `timeout`, `429`, `503`, `overloaded`, `modelapierror`, `readtimeout`, `connection`). Those are worth re-running because the timeout was infrastructure noise, not a real budget issue. Pure-budget timeouts are left alone (re-running won't change the outcome).

After dry-run confirms the candidate set:

```bash
VIRTUAL_ENV= uv run --no-sync python scripts/rerun_network_impacted.py
```

This moves the bad new runs to `_failed_network_timeout/`, restores the old runs from `_superseded/`, and resets state entries to `queued`. Then re-run the layer-0 orchestrator to re-execute them.

### Step 6b — Parallel re-run alongside a running orchestrator

If the layer-0 orchestrator is still in flight and you want to re-execute the network-impacted set without killing it, use `rerun_18_parallel.py` instead. It writes to a SEPARATE `rerun_18_state.json` and merges back at the end. Concurrency is a single `asyncio.Semaphore(6)`.

```bash
nohup bash -c 'VIRTUAL_ENV= uv run --no-sync python scripts/rerun_18_parallel.py \
  >> /tmp/rerun_18_parallel.log 2>&1' > /tmp/rerun_18_parallel.stdout 2>&1 &
disown
```

After both batches drain, merge the side-state into main:

```python
# scripts-style one-liner — overwrites new_run_id / new_run_dir for entries
# that were re-executed via the parallel batch.
```

(See the inline script in the conversation/commit history under "merged 18 entries from side -> main".)

### Step 7 — Run layer 1

`run_rerun_plan.py --layer 1` only starts once every in-scope layer-0 entry is `archived` or `excluded`. The `excluded` status is set manually for specs that reference a model on the excluded list (e.g. mixed-model specs where one agent uses Llama).

```bash
nohup bash -c 'VIRTUAL_ENV= uv run --no-sync python scripts/run_rerun_plan.py --layer 1 \
  >> /tmp/layer1_orchestrator.log 2>&1' > /tmp/layer1_orchestrator.stdout 2>&1 &
disown
```

Layer 1's placeholders all resolve through the merged `rerun_state.json`: every parent's `new_run_dir` field carries the fresh dir produced by layer 0.

### Step 8 — Regenerate sidecars

After layer 1 finishes, re-run steps 1 + 2 against the now-cleaned cohort:

```bash
VIRTUAL_ENV= uv run --no-sync python scripts/replay_veyru_judge.py
VIRTUAL_ENV= uv run --no-sync python scripts/write_judge_replay_sidecars.py
```

The FE / streamlit "Judge replay" tab should now show ~0 flips for the rerun cohort. Runs that were excluded (Qwen / Llama) still carry their old sidecars unchanged.

### Step 9 — Run the heavy metrics on the cleaned cohort

The rerun orchestrator deliberately skips the expensive metric families (`SKIP_METRICS` in `run_rerun_plan.py`: `protocol_probe*`, `communication_open_coding`, `communication_feature_presence`) to keep eval cost bounded during a multi-hundred-run pass. Run them separately when the cohort is stable:

```bash
# protocol probe (requires --probe-replicas N, optionally --probe-round R)
schmidt evaluate veyru --run-dir runs/veyru/<id> --metrics protocol_probe \
  --probe-replicas 3 --model claude-haiku-4-5-20251001 --provider anthropic

# communication open coding → consolidate → feature presence
schmidt evaluate veyru --run-dir runs/veyru/<id> --metrics communication_open_coding \
  --model claude-haiku-4-5-20251001 --provider anthropic
VIRTUAL_ENV= uv run --no-sync python scripts/consolidate_communication_ontology.py
schmidt evaluate veyru --run-dir runs/veyru/<id> --metrics communication_feature_presence \
  --ontology-path runs/veyru/_ontology/<version>.json \
  --model claude-haiku-4-5-20251001 --provider anthropic
```

## What happens to the data

For each successfully re-executed spec `<old>` → `<new>`:

1. The new sim's dir is `runs/<scenario>/<new>`. It carries all the usual artifacts (`veyru.jsonl`, `veyru_report.json`, `labels.json`, per-agent resume contexts where applicable). Labels are the predecessor's domain labels (minus `eval:*`) plus `supersedes:<old>`.
2. The predecessor moves to `runs/_superseded/<scenario>/<old>/`. A `superseded_by.json` file in that dir points at the new run.
3. The state entry in `rerun_state.json` records the full transition history: `queued` → `launched` → `sim_ended` → `evaluated` → `archived`, each with timestamps.
4. The FE list view's `supersedes:<old>` label makes the new run discoverable. The streamlit Baseline tab (and every other tab) will show the new run; the old is filtered out via the slider.

For specs that got re-executed via `rerun_18_parallel.py`:

5. The previously-archived (failed) new run dir moves to `runs/_failed_network_timeout/<scenario>/<failed_new_id>/`.
6. The predecessor's `_superseded/<old>/superseded_by.json` is rewritten to point at the fresh new dir.

For excluded specs (`status="excluded"`):

7. Nothing on disk changes. The state entry just records "this spec won't be re-run" with a reason.

## Re-running the pipeline from scratch

To repeat the exercise after another judge-prompt change:

1. Pull current `rerun_state.json` aside (or delete it — it's a cache).
2. `python scripts/replay_veyru_judge.py` (will re-judge under the new prompt; cache hits keep prior verdicts).
3. `python scripts/write_judge_replay_sidecars.py`.
4. `python scripts/build_rerun_plan.py --threshold 0.20` (tune threshold).
5. Layer 0 → recovery → network-impacted re-run → merge → layer 1 → re-replay → sidecars.

The scripts are idempotent: re-running step N picks up where the prior invocation left off (state-driven) and skips anything already `archived` / `excluded`.

## Knobs worth tuning

In `scripts/run_rerun_plan.py`:

- `PER_PROVIDER_CONCURRENCY` — anthropic + openai each get this many concurrent slots. Default 10. Comfortable up to 12 per provider for current accounts.
- `SIM_WAIT_TIMEOUT_SEC` — how long to wait for `simulation_ended` before giving up. Default 180 min. Multi-swap 60-round opus specs can take 2–3 hours; bump if you see widespread `sim_wait_timeout` errors.
- `EVAL_TIMEOUT_SEC` — per-spec `schmidt evaluate` cap. Default 20 min.
- `SKIP_METRICS` — metric names dropped from the predecessor's metric set during the rerun pass to keep cost bounded.
- `REMOVED_METRICS` — metric names that were renamed in the codebase but still appear in older reports.
- `SCHEMA_EVOLUTION_DEFAULTS` — knob fields added to scenarios after older runs were created. Filled in to make old configs validate against current code.
- `AGENT_ID_RENAMES` — historical agent IDs renamed in the codebase (e.g. `specialist` → `stabilization_engineer`). Rewritten in `agents.<id>.*` CLI overrides before launch.
