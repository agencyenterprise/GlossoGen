# Multi-swap baseline — postmortem always on (sonnet) — 2026-05-22

## Goal
Sibling cohort to [../2026-05-22_multi_swap_baseline_sonnet](../2026-05-22_multi_swap_baseline_sonnet/).
Identical knobs (budget=450, phases=A10-B10-C10-D10, sonnet-4-6, seed=42,
history=10) except **postmortem stays enabled across all 4 phases** — the
sibling cohort disables postmortem at the start of Phase B (round 11).

Paired with the sibling so we can measure how much of the round_success and
language-emergence trajectory in the base cohort is driven by the postmortem
channel being on/off vs. by the swap pattern itself.

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
| `seed` | 42 |

**Difference from sibling**: `scheduled_events` omits the
`set_postmortem(at_round=11, enabled=false)` entry. The 3 swap events at
rounds 11/21/31 are unchanged.

## Phase structure
| Phase | Rounds | Length | Postmortem | Swap at start | History visible |
|-------|--------|--------|------------|---------------|-----------------|
| A | 1–10 | 10 | on | — | n/a |
| B | 11–20 | 10 | **on** (← sibling: off) | field_observer@11 | link from round 1 |
| C | 21–30 | 10 | **on** | stabilization_engineer@21 | link from round 11 |
| D | 31–40 | 10 | **on** | field_observer@31 | link from round 21 |

## Cohort
- 10 fully independent `glossogen run` invocations, seed=42, cap=6 concurrent
- Labels: `["multi_swap_baseline_postmortem_on", "budget=450", "phases=A10-B10-C10-D10", "history=10"]`

## Launch
Deferred — fires after the sibling cohort's launcher completes (so both
launchers don't compete for sonnet slots simultaneously). Trigger:
```bash
nohup bash experiments/2026-05-22_multi_swap_baseline_postmortem_on_sonnet/launch.sh \
  > /tmp/multi_swap_baseline_postmortem_on_sonnet.stdout 2>&1 &
disown
```

Launcher log: `/tmp/multi_swap_baseline_postmortem_on_sonnet.log`.

## Evaluation pipeline
Identical to the sibling cohort — same `glossogen evaluate` invocations with
the same metric set, same 4 probe cutoffs (11, 21, 31, 41).

## Analysis
The two cohorts plot **on the same axes** so the postmortem effect is visible
as the gap between the two curves:
- Round-success curve: two lines (postmortem-off / postmortem-on) per round
- Phase-end pair similarity: two grouped points per phase

## Cohort run IDs
*(filled in as launches land)*

| # | Run ID | Status | Reports | Notes |
|---|--------|--------|---------|-------|
| 1 | veyru/1779477671 | running | — | launched 16:21 |
| 2 |  | pending |  |  |
| 3 |  | pending |  |  |
| 4 |  | pending |  |  |
| 5 |  | pending |  |  |
| 6 |  | pending |  |  |
| 7 |  | pending |  |  |
| 8 |  | pending |  |  |
| 9 |  | pending |  |  |
| 10 |  | pending |  |  |
