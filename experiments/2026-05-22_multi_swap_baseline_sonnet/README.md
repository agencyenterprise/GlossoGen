# Multi-swap baseline (sonnet) — 2026-05-22

## Goal
A clean, independent 10-replica baseline cohort to measure (a) how round_success
evolves round-by-round across a 4-phase multi-swap timeline, and (b) how the
agents' protocol diverges between agent pairs at the end of each phase.

Replaces the ad-hoc Phase-1+Phase-3 baselines that mixed seeds, mixed source
runs, and used a forked/resumed timeline. This cohort is built from scratch —
each run starts at round 1 with no shared parent.

## Knobs (`knobs.json`)
| Knob | Value |
|------|-------|
| `round_time_budget_seconds` | 450 |
| `round_count` | 40 |
| `easy_round_numbers` | `[1, 2, 3, 6, 13]` |
| `postmortem_enabled` | true |
| `postmortem_after_swap` | true |
| `channel_noise_level` | 0.0 |
| `judge_model` | `claude-haiku-4-5-20251001` |
| `judge_provider` | `anthropic` |
| `seed` | 42 (inherited from veyru default) |

## Phase structure
| Phase | Rounds | Length | Postmortem | Swap at start | History visible |
|-------|--------|--------|------------|---------------|-----------------|
| A | 1–10 | 10 | on | — (initial agents) | n/a |
| B | 11–20 | 10 | off (set_postmortem@11) | field_observer@11 | link from round 1 |
| C | 21–30 | 10 | off | stabilization_engineer@21 | link from round 11 |
| D | 31–40 | 10 | off | field_observer@31 | link from round 21 |

Each swapped-in agent sees the previous 10 rounds of link channel history (the
postmortem channel becomes globally disabled at round 11, so swap reconstruction
strips it from B/C/D regardless of visibility config).

## Cohort
- Model: `claude-sonnet-4-6` (anthropic), all rounds, all agents
- Judge: `claude-haiku-4-5-20251001`
- Seed: 42 across all 10 replicas (canonical — identical case set, measures
  pure LLM stochasticity on identical workload)
- 10 fully independent `glossogen run` invocations (no fork, no resume)
- Concurrency cap: 6 sonnet sims at a time
- Labels: `["multi_swap_baseline", "budget=450", "phases=A10-B10-C10-D10", "history=10"]`

## Launch
```bash
nohup bash experiments/2026-05-22_multi_swap_baseline_sonnet/launch.sh \
  > /tmp/multi_swap_baseline_sonnet.stdout 2>&1 &
disown
```

Launcher log: `/tmp/multi_swap_baseline_sonnet.log`.
Per-replica stdout: `/tmp/multi_swap_baseline_rep{1..10}.log`.

## Evaluation pipeline (per run, after sim ends)
1. **Standard metrics** — judge `claude-haiku-4-5-20251001`:
   ```
   glossogen evaluate veyru --run-dir <dir> \
     --metrics round_success,perplexity,mean_chars_per_round,mean_chars_per_message,language_strangeness,neologism,slang_emergence,shorthand_codes,communication_open_coding,communication_feature_presence \
     --model claude-haiku-4-5-20251001 --provider anthropic
   ```
2. **Probe at 4 cutoffs** — agent's own model (`claude-sonnet-4-6`); each call
   appends rows to `protocol_probe_responses.jsonl`:
   ```
   for cutoff in 11 21 31 41; do
     glossogen evaluate veyru --run-dir <dir> \
       --metrics protocol_probe --probe-replicas 3 --probe-round $cutoff \
       --model claude-sonnet-4-6 --provider anthropic
   done
   ```
   Cutoffs map to end-of-phase: 11→A, 21→B, 31→C, 41→D.
3. **Probe similarity summaries** — reads the accumulated JSONL:
   ```
   glossogen evaluate veyru --run-dir <dir> \
     --metrics protocol_probe_replica_self_similarity,protocol_probe_agent_pair_similarity,protocol_probe_cutoff_trajectory \
     --model claude-haiku-4-5-20251001 --provider anthropic
   ```

## Analysis (plots)
| Plot | X | Y | Source |
|------|---|---|--------|
| Round-success curve | round (1–40) | success rate (0–1) across 10 runs ± SE | `RoundResultRecorded` events |
| Phase-end pair similarity | phase A/B/C/D | mean agent-pair similarity across 10 runs ± SE | `protocol_probe_agent_pair_similarity.json` |

Scripts (to be written):
- `analysis/scripts/multi_swap_baseline_round_success.py`
- `analysis/scripts/multi_swap_baseline_probe_similarity.py`

## Cohort run IDs
*(filled in as launches land)*

| # | Run ID | Status | Reports | Notes |
|---|--------|--------|---------|-------|
| 1 | veyru/1779473397 | wrapping (r=40) | — | smoke test |
| 2 | veyru/1779473436 | **dead at r=22** | — | MCP 404 spiral, excluded |
| 3 | veyru/1779473543 | done | ✓ |       |
| 4 | veyru/1779473551 | running | — |       |
| 5 | veyru/1779473558 | wrapping (r=40) | — |       |
| 6 | veyru/1779473565 | wrapping (r=40) | — |       |
| 7 | veyru/1779476007 | running | — |       |
| 8 | veyru/1779476617 | running | — |       |
| 9 | veyru/1779477407 | running | — |       |
| 10 | veyru/1779477475 | running | — |       |
| 11 (backfill) | veyru/1779477672 | running | — | replacement for dead rep 2 |
