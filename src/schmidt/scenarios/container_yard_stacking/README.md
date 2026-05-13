# Scenario: Container Yard Stacking

Three agents — a yard operator who dispatches the inbound and outbound robotic trucks, a logistics planner who holds the per-round yard map, and a crane operator who executes one physical crane move per tool call — coordinate over a shared link channel to place one incoming container into its correct slot each round. The container has to clear a customs inspection at the slot, and the inspection slot is only held open for a fixed window per round: every character sent on the link channel costs one second of that window, and if the round runs over, the inspection is missed and the round fails. The map (active crane stations, the two named transfer pads at each station, which stacks each station reaches, current stack layout, shift manifest) reshuffles every round, so postmortem discussions can only teach communication conventions — never "ship type X to crane Y".

## Domain

A small section of a container yard: four stacks of fixed height 3. Two named transfer pads per crane station (`north_pad` / `south_pad` / ... freshly drawn each round). Each round one inbound container arrives on a robotic truck and must end at a specific (stack, tier) slot. Two crane stations are active per round, each reaching a disjoint subset of stacks — exactly one of them can reach the target stack.

Each round, the planner sees a **shift manifest** listing four candidate `(container_id → target slot)` entries. Exactly one of those entries is the container actually on the inbound truck this round; the rest are decoys. The yard operator alone sees the incoming container's ID, so the planner cannot pick which manifest entry is active — and therefore cannot pick the correct station, pads, or crane plan — without the yard operator first sharing the container ID on the link channel.

Two round types are generated, with the order shuffled per seed:

- **No-blocker rounds** (~60% of rounds): the active target tier is the next-empty tier on top of an empty or partial stack. The yard operator sends one inbound truck; the crane plan is one move: inbound truck → target tier.
- **Blocker rounds** (~40%): the active target tier is currently occupied by one container. The yard operator sends two trucks (an inbound truck carrying the incoming container and an empty outbound truck) both to the correct station but at different pads. The crane plan is two moves: blocker → outbound truck, then incoming → the now-vacated target tier. The outbound truck leaves loaded with the blocker.

Round difficulty is not a user knob. For a given `round_count` the case generator produces a deterministic count of blocker rounds (currently `round(0.4 * round_count)`) and shuffles the order with the seeded RNG, so each seed sees a different running order but the same total. Decoy manifest entries independently roll the same blocker probability, so blocker/no-blocker entries appear in the manifest in the same mix as real cases — the planner cannot infer the active entry from "which one has a blocker".

## Agents

### Yard Operator

Sees only the incoming container's ID. Cannot see the yard map, active crane stations, the available pads, the shift manifest, or the target slot. The only agent that can call `move_truck`. Each round they may commit up to two trucks (an inbound truck always; an outbound truck when the planner asks for one).

### Logistics Planner

Holds the round's dynamic yard map: which two crane stations are active, the two transfer pads at each station, which stacks each station reaches, the current four-stack layout (bottom-to-top per stack), and the shift manifest of candidate `(container_id → target slot)` entries. Cannot see the incoming container's ID, so cannot pick which manifest entry is active. Cannot call any tool other than `send_message` — must route the truck assignments to the yard operator and the ordered crane plan to the crane operator.

### Crane Operator

Sees only their idle crane and the link channel. Cannot see the yard map, the incoming container's ID, the manifest, or the target slot. The only agent that can call `place_on_stack` and `lift_from_stack`, and must call them once per physical move in the order the planner provides.

## Channels

| Channel ID    | Display Name     | Members                                       | Notes                      |
|---------------|------------------|-----------------------------------------------|----------------------------|
| link          | link             | Yard Operator, Logistics Planner, Crane Op    | Inspection-window-bound    |
| postmortem    | team discussion  | Yard Operator, Logistics Planner, Crane Op    | Free discussion (when on)  |

The link channel is the primary channel where character costs apply. The postmortem channel is available during the discussion phase and does not consume the window.

## Tools

**`send_message(channel_id: str, text: str)`** — All three agents. Sends a message to a channel. On the link channel, every character costs one simulated second against the round's `time_budget_seconds` inspection window.

**`move_truck(truck_role, station_name, pad, container_id)`** — Yard Operator only. Structured Pydantic-typed args, all compared by **strict equality** to the case ground truth (case-sensitive, no normalization, no shorthand):
- `truck_role: Literal["inbound", "outbound"]` — which truck is being committed.
- `station_name: str` — must exactly match the canonical station name from the planner's active-stations list (e.g. `"crane_station_one"`).
- `pad: str` — must exactly match one of the correct station's pad names (e.g. `"north_pad"`) and must not already be committed to another truck this round.
- `container_id: str` — must exactly match the assignment's container_id (the incoming container's ID for inbound trucks; the empty string for outbound trucks).

The world validates each call deterministically against the case ground truth and the live truck-commit state. Verdict flags: role matches an active assignment, station matches, pad belongs to the correct station and is not already committed to another truck, container matches. Any mismatch flips the round to a terminal failure.

**`place_on_stack(container_id, stack, tier)`** — Crane Operator only. Drops the incoming container off the inbound truck and places it at `(stack, tier)`. `tier` must be the next-empty tier above the destination stack's current top.

**`lift_from_stack(container_id, stack, tier)`** — Crane Operator only. Lifts the container currently at `(stack, tier)` onto the outbound truck (which leaves loaded). `tier` must be the topmost occupied tier of the source stack.

The world deterministically validates each move against `expected_move_sequence[accepted_move_count]` and the live world state (stacks + truck positions + truck contents), and mutates state on accept. A mismatch flips the round to a terminal failure. The scenario soft-rejects (no terminal flip) when the operator calls the tool before the truck required by the next expected step has arrived — the operator can retry once the yard operator commits the missing truck.

## Round Flow

1. Round starts — each agent receives a per-role injection. All three see the round's inspection window. The yard operator additionally sees the incoming container's ID. The planner additionally sees the dynamic yard map, active stations and pads, current stacks, and the shift manifest. The crane operator's injection carries no case-specific information.
2. Yard operator reports the container ID to the planner on the link channel.
3. Planner finds the manifest entry whose `container_id` matches, takes that entry's target slot, picks the crane station whose `reachable_stacks` covers the target stack, assigns one of its two pads to the inbound truck, and — if the target tier is currently occupied — assigns the other pad to the outbound truck. The planner relays these assignments to the yard operator.
4. Yard operator calls `move_truck(...)` once for the inbound truck, and a second time for the outbound truck on blocker rounds. After each call the world emits `<ROLE> TRUCK ARRIVED AT CORRECT SPOT` on success or `<ROLE> TRUCK ARRIVED AT WRONG SPOT` (and marks the round terminally failed) on any mismatch.
5. Planner sends the ordered crane plan to the crane operator (one move when there is no blocker, two when there is).
6. Crane operator calls `place_on_stack(...)` (and on rounds with a blocker, `lift_from_stack(...)` first) once per physical move. The world validates against `expected_move_sequence[accepted_move_count]` and the live world snapshot and mutates state on accept. A reject marks the round terminally failed.
7. World tracks cumulative character cost on the link channel; sends a `CRITICAL` notification at 75% of the window and a `COMMUNICATION BUDGET EXCEEDED` notification at 100% (the latter also marks the round terminally failed).
8. The round ends early via `get_early_round_end_trigger` when the incoming container reaches its target tier with the full expected plan accepted (`round_completed`) or the world rules the round terminally failed (`round_failed`). Otherwise it ends via `all_agents_idle` or `round_timeout`.
9. At round end the world emits exactly one terminal notification carrying either `ROUND SUCCESS` or `ROUND FAILED. <reason>`.
10. Discussion phase — all three agents can talk freely in the postmortem channel (when enabled). Messages here do not cost time.
11. Next round begins with a fresh case.

## Case Generation

Cases are generated procedurally from `seed`. Each round draws:

1. **Incoming container** — random unique ID like `Orion-742`.
2. **Target stack** — uniform over `[1, STACK_COUNT]`.
3. **Round type** — pre-baked from a shuffled list with `round(0.4 * round_count)` blocker rounds and the rest no-blocker rounds.
4. **Stack pre-state** — target stack starts with `target_stack_height` filler containers stacked bottom-up. Other stacks get 0–2 random filler containers each. For a no-blocker round `target_stack_height = randint(0, STACK_HEIGHT - 1)` and the target tier is one above; for a blocker round `target_stack_height = randint(1, STACK_HEIGHT)` and the target tier is the currently-top tier (the blocker is moved aside before the incoming container lands there). Blocker rounds cover tiers `1..STACK_HEIGHT`, including a fully-stacked target where the blocker sits at the top tier.
5. **Active crane stations** — two stations are sampled (fresh names and pads each round), with `STACK_COUNT // 2` disjoint reachable stacks each. Each station gets `PADS_PER_STATION` (=2) freshly named pads drawn from a shared pool. The station that reaches the target stack is recorded as `correct_crane_station`.
6. **Truck assignments** — the case fixes the station and (for inbound) the container, but NOT the pad. The planner picks pads at runtime from the correct station's pad list. On blocker rounds the two trucks must use different pads of that station; the world enforces this. The world records each planner-chosen pad in `truck_states[role].pad` once the commit is accepted.
7. **Expected move sequence** — derived from steps 1–6, stored as structured `CraneMoveStep` records: `(move_index, container_id, source_kind, source_stack, source_tier, destination_kind, destination_stack, destination_tier)`. Truck endpoints (`inbound_truck`/`outbound_truck`) carry `None` for stack/tier; stack endpoints carry both. The world compares the agent's submitted move structurally against this record — no string rendering or pad substitution. No blocker: one move (inbound truck → target tier). Blocker: two moves (blocker tier → outbound truck; inbound truck → blocker's former tier).
8. **Shift manifest** — the real entry `(incoming_container_id → target slot)` is mixed with three decoy entries and shuffled. Each decoy gets a fresh container ID and a structurally valid target slot drawn independently with the same blocker probability as a real case. Targets are distinct from the real one and from each other so each manifest entry points at a unique slot.

The same canonical seed (`42` per `CLAUDE.md`) produces the same sequence of cases across runs, so cross-model comparisons see an identical workload.

## Why Postmortem Cannot Memorize

The planner's `(correct crane station, two pads, target stack, target tier, expected blocker, manifest entries)` tuple is re-sampled every round. The yard operator's container ID is re-sampled every round. Both station-to-stack reachability and the set of currently-stacked containers reshuffle, so a fixed mapping like "Stack 2 → Crane Two" cannot solve a future round. What postmortem can teach is purely communicative: shorthand for the container-ID handoff, shorthand for truck assignments and stack-tier addresses, a compact representation for the two-move crane plan, etc. These are exactly the protocol features the language metrics target.

## Budget and Failure Mechanics

The world counts characters on the link channel only — postmortem stays free. Notifications fire at:

1. **75% of window** — `CRITICAL: Yard window narrowing. <remaining> seconds of budget remaining.`
2. **100%+ of window** — `COMMUNICATION BUDGET EXCEEDED. Communication time: <chars> chars exceeded budget of <budget>s.` This also flips `round_failed_terminally` so the round ends on the next `get_early_round_end_trigger` poll.

Three terminal-failure paths:

- A `move_truck` call fails any of (role matches an active assignment, station, pad, container) → world emits `<ROLE> TRUCK ARRIVED AT WRONG SPOT` and the round fails.
- A `place_on_stack` or `lift_from_stack` call fails matches-expected / source-holds-container / destination-empty / direction-valid → world rejects the move and the round fails.
- Character cost on the link channel reaches the inspection window → world emits `COMMUNICATION BUDGET EXCEEDED` and the round fails.

A round only succeeds if every expected truck was committed correctly, the crane operator submitted every move in `expected_move_sequence` and each was accepted, the incoming container is at its target tier, and the inspection window was not exhausted. Rounds where all three agents go idle before the work is finished end via the `all_agents_idle` trigger and are reported in the next postmortem as `INCOMPLETE — everyone stopped acting before container X reached Y`.

## Evaluation

The scenario implements one specific metric and inherits all generic metrics through `_get_metrics()` + `super().get_available_metric_names()`.

**`round_success`** — Deterministic; no LLM judge. Reads from the JSONL: `RoundAdvanced` (round count), `ContainerYardCaseStarted` (expected truck count + expected move count), `ContainerYardTruckJudged` (per-truck verdicts), `ContainerYardCraneMoveJudged` (per-round count of accepted moves), and `WorldEventDelivered` (matches `ROUND_SUCCESS_MARKER` and `BUDGET_EXCEEDED_MARKER`). A round counts as success only when every expected truck role produced an `overall_success=true` truck event and all expected moves were accepted. Emits one Measurement with `score = succeeded / total_rounds`, plus a per-round observation explaining the first failure mode it sees.

Useful generic metrics for this scenario:

- **`mean_chars_per_round`** — Total link-channel characters per round, averaged. Directly comparable to `time_budget_seconds` (one character = one second).
- **`mean_chars_per_message`** — Per-message verbosity; removes the inflation that comes from round-by-round message count differences (blocker rounds need more back-and-forth than no-blocker rounds).
- **`perplexity`** — Mean per-token surprisal of link-channel messages under `gpt2`. Lower under heavy compression, higher under natural-language verbosity.
- **`language_strangeness` / `slang_emergence` / `neologism` / `shorthand_codes`** — LLM-judged emergent-language metrics from the generic registry; the link channel returned by `get_primary_channel_id()` is what they read.
- **`round_ended_idle` / `round_ended_timeout`** — Flag rounds that ended via agent idle vs wall-clock timeout (vs the more-common `round_completed` / `round_failed` scenario triggers).
- **`content_filter_refusal`** — Counts `AgentRunCycleFailed` events with `error_type == ContentFilterError`.

## Knobs

| Knob                              | Description                                                                                                                        |
|-----------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| `round_count`                     | Number of rounds                                                                                                                   |
| `time_budget_seconds`             | Per-round customs inspection window (one character on the link channel = one simulated second)                                     |
| `seed`                            | Controls case generation (containers, stacks, stations, pads, manifest decoys, blocker-round shuffle)                              |
| `channel_noise_level`             | Per-character drop probability on the link channel only (postmortem stays clean). In `[0.0, 1.0]`. Dropped chars become `_`        |
| `postmortem_enabled`              | Whether a discussion phase follows each round                                                                                      |
| `postmortem_disabled_at_start`    | When true, postmortem is dropped from round 1 onward. Used by replace-agent / cross-run flows                                      |
| `postmortem_duration_seconds`     | Time limit for the discussion phase (inherited from `BaseKnobs`)                                                                   |
| `max_round_duration_seconds`      | Wall-clock timeout per round (inherited)                                                                                           |
| `model_overrides`                 | Per-agent model/provider overrides (inherited)                                                                                     |
| `agent_max_tokens`                | Per-cycle output-token cap (inherited from `BaseKnobs`)                                                                            |
| `replace_agent_default_channel_visibility` | Platform knob — empty by default, so both `link` and `postmortem` default to visible after a replace-agent swap. Postmortem tool calls in the replaced agent's reconstructed history are blocked separately via `get_replace_agent_blocked_tool_call_channels()` |
| `scheduled_events`                | Platform knob — round-keyed `swap_agent` and `set_postmortem` events fired by the in-run scheduler                                 |

## Presets

- `knobs_default.json` — 15 rounds, 200 sec/round inspection window, lossless link channel, postmortem enabled.

## Running

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt run container_yard_stacking \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config src/schmidt/scenarios/container_yard_stacking/knobs_default.json \
  > ./runs/container_yard_stacking_stdout.log 2>&1 &
```

After completion, score with:

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt evaluate container_yard_stacking \
  --run-dir ./runs/container_yard_stacking/<timestamp> \
  --metrics round_success,mean_chars_per_round,mean_chars_per_message \
  --model claude-haiku-4-5-20251001 --provider anthropic
```
