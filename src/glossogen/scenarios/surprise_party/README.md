# surprise_party

Three friends share one group chat:

- **Alice** (persistent) — knows a fixed `(where, when)` surprise-party detail for Chris and must communicate it across rounds.
- **The Friend slot** — filled by a fresh agent with a new name every round. The friend has no chat history at the start of each round and must decode the secret from that round's chat alone.
- **Chris** (persistent adversary) — the guest of honor. Accumulates every round's chat. If Chris ever decodes the secret, the simulation ends.

Both the Friend and Chris each have a `submit_guess` tool with freetext `where` and `when` args. An LLM judge (canonical haiku) compares the guess against the ground truth with lenient matching. The round ends as soon as anyone is judged correct.

## Round outcomes

| Outcome | Effect |
|---|---|
| Friend correct | Round success. Next round's Friend swaps in fresh. |
| Chris correct | Round failure. Simulation terminates immediately via `is_finished_early()`. |
| Wall-clock timeout | Round failure (no exposure, no win). Continue. |

## Mechanism

The Friend's per-round freshness is implemented with the platform's `scheduled_events` / `swap_agent` machinery. The scenario generates one `SwapAgent` per round 2..N at construction time and emits them via `get_scenario_config()`. Each swap sets `channel_visibility["chat"] = {"kind": "from_round", "round_floor": R}` so the swapped-in friend's seed history is empty.

Per-round friend names are drawn deterministically from a seeded shuffle of `FRIEND_NAME_POOL`. The chat renders historical messages under the per-round name (e.g. round-1 messages stay as "Mary: ..." even when read from round 3) via the platform helper `get_agent_display_name_at_round(agent_id, round_number)`.

## Knobs

| Knob | Type | Purpose |
|---|---|---|
| `judge_model` / `judge_provider` | str / str | LLM judge for `submit_guess` |
| `round_count` | int | Total number of rounds |
| `compaction.enabled` / `compaction.token_threshold` | bool / int | Opt-in provider-native history compaction (Anthropic/OpenAI), off by default; summarizes older messages once input tokens exceed the threshold (inherited from base) |
| `seed` | int | Drives `(where, when)` draw and friend-name shuffle |
| `friend_model` / `friend_provider` | str / str | Pins the Friend slot's model across initial spawn + every swap |
| (inherited) `max_round_duration_seconds` | float | Per-round wall-clock timeout |

## Running

```bash
glossogen run surprise_party \
  --model claude-haiku-4-5-20251001 --provider anthropic --runs-dir ./runs \
  --config src/glossogen/scenarios/surprise_party/knobs_default.json
```
