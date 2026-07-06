# Scenario: Spillway Release

Three agents jointly manage a reservoir each round: keep the dam from collapsing **and** from draining to shortage, without ever sending a gate release down the river while the downstream hiking park is occupied. The information needed to act is split three ways, so the team must coordinate over a shared, communication-budgeted channel every round. Scoring is fully deterministic — there is no LLM judge.

## Agents

| Agent | Private information (per round) | Tools |
|---|---|---|
| **Dam operator** | the current reservoir level (gauge) | `read_gauge`, `open_gates` |
| **Civil defense** | the weather forecast: conditions + exact inflow | `evacuate` |
| **Park ranger** | the park schedule: opening time, visitors, whether it can be closed | `notify_park` |

All three share the current wall-clock time. None can see the others' private information, so the operator cannot pick a correct gate setting without civil defense's inflow, nor decide whether a release is safe without the ranger's park schedule.

## Channels

| Channel ID | Display name | Members | Notes |
|---|---|---|---|
| `ops` | ops | all three | Budget-constrained primary channel; optional per-character noise |
| `postmortem` | team discussion | all three | Free discussion when enabled; does not cost budget |

The `ops` channel is the primary channel where the per-round character budget applies (one character = one simulated second).

## Physics

`gate_count` identical gates, each shedding `release_per_gate_per_hour`% of capacity per hour. The operator calls `open_gates(count, duration_hours)`; total shed = `count × release_per_gate_per_hour × duration_hours`, over the window `[current_time, current_time + duration_hours]`.

- `end_level = start_level + inflow − shed`
- The dam collapses above `max_level`%; the supply fails below `min_level`%. The end-of-round level must land in `[min_level, max_level]`.
- The park is occupied from its opening time to the end of the operating day. **Any** release whose window overlaps the occupied window is unsafe unless the downstream area is cleared.

## Three safe paths for a release

| Path | Owner | Use when |
|---|---|---|
| Finish the release before the park opens | dam operator | enough gates × pre-opening hours to shed what's needed |
| Close / keep the park closed | park ranger | the release must overlap opening **and** the park is closeable |
| Evacuate | civil defense | the release must overlap opening **and** the park is committed-open (not closeable) |

## Round success (all four clauses)

1. **Dam safe** — `min_level ≤ end_level ≤ max_level`.
2. **No casualties** — no release window overlapped an occupied, uncleared park.
3. **No needless closure** — the ranger secured the park only when a release would otherwise have endangered visitors.
4. **No false alarm** — civil defense evacuated only when clearing was needed **and** the park could not be closed.

A round also fails if the `ops` communication budget is exhausted.

## Round archetypes

Each non-warmup round is one of four archetypes drawn from `archetype_weights` (order: `hold`, `time_it`, `keep_closed`, `evacuate`):

- **hold** — holding (zero gates) keeps the level in band; correct play clears nothing.
- **time_it** — a release is needed but the park opens later and the shed fits before opening; correct play releases early, clears nothing.
- **keep_closed** — a release is needed while the park is already open and closure is permitted; the ranger closes the park.
- **evacuate** — a release is needed while the park is committed-open; civil defense evacuates.

Rounds in `easy_round_numbers` are forced to `hold` as warmups.

## Knobs

| Knob | Description |
|---|---|
| `round_count` | Number of rounds |
| `round_time_budget_seconds` | Per-round character budget on the ops channel |
| `compaction.enabled` / `compaction.token_threshold` | Opt-in provider-native history compaction (Anthropic/OpenAI), off by default; the provider summarizes older messages once an agent's input tokens exceed the threshold (inherited from base) |
| `seed` | Case-generation seed |
| `postmortem_enabled` / `postmortem_disabled_at_start` / `postmortem_duration_seconds` | Discussion phase controls |
| `channel_noise_level` / `noise_replacement_mode` | Per-character ops-channel noise (`mask` erasure / `random_letter` substitution) |
| `easy_round_numbers` | Rounds forced to the `hold` archetype |
| `gate_count` / `release_per_gate_per_hour` | Spillway physics |
| `max_level` / `min_level` | Reservoir safe band |
| `day_end_hours` | End of the operating-day horizon |
| `archetype_weights` | Positional weights for `[hold, time_it, keep_closed, evacuate]` |

## Evaluation

Spillway opts into the platform metrics by implementing `judge_round_result` (deterministic per-round success) and `get_primary_channels` (the `ops` channel). It ships no scenario-private metrics. Useful metrics: `round_success`, `mean_chars_per_round`, `mean_chars_per_message`, `perplexity`, the language-emergence metrics, `shorthand_codes`, `neologism`, and `content_filter_refusal`.

```bash
python -m schmidt run spillway_release \
  --model gpt-5.4 --provider openai \
  --runs-dir ./runs \
  --config src/schmidt/scenarios/spillway_release/knobs_default.json
```
