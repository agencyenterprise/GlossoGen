# Scenario: Container Yard Stacking

Three agents — a yard operator who dispatches the robotic truck, a logistics planner who holds the per-round yard map, and a crane operator who executes one physical crane move per tool call — coordinate over a shared coordination channel to place one incoming container into its correct slot each round. Every character sent on the coordination channel costs one simulated second; if total communication time exceeds the round's budget, the round fails. The map (active crane stations, which stacks each station reaches, current stack layout, target slot, and the temp-slot inventory) reshuffles every round, so postmortem discussions can only teach communication conventions — never "ship type X to crane Y".

## Domain

A small section of a container yard: one block (Block Delta), one bay (Bay Seven), four stacks of fixed height 3, two named temporary holding slots ("temp slot Alpha" / "temp slot Bravo"). Each round one inbound container arrives on a robotic truck and must end at a specific (stack, tier) slot. Two crane stations are active per round, each reaching a disjoint subset of stacks — exactly one of them can reach the target stack. Two case difficulties are generated:

- **Easy** (~60% with the default `hard_case_fraction=0.4`): the target tier is the next-empty tier on top of an empty or partial stack. The crane plan is one move: truck → target tier.
- **Hard** (~40%): the target tier is currently occupied by one "blocker" container. The crane plan is two moves: blocker → temp slot, then truck → target tier (the now-vacated slot). No restore step is performed in v1 — the blocker stays at the temp slot.

## Agents

### Yard Operator

Sees only the incoming container's manifest: identity, size class ("forty-foot high-cube" / "forty-foot standard" / "twenty-foot standard"), loaded weight in metric tons, and departure group ("north" / "south" / "east" / "west"). Cannot see the yard map, active crane stations, or the target slot. The only agent that can call `move_truck_to_crane_spot`.

### Logistics Planner

Holds the round's dynamic yard map: which two crane stations are active and which stacks each reaches, the current four-stack layout (bottom-to-top per stack), the target final position for the incoming container, and the available temp-slot inventory. Cannot see the incoming container's manifest. Cannot call any tool other than `send_message` — must route the truck instruction to the yard operator and the ordered crane plan to the crane operator.

### Crane Operator

Sees only their idle crane and the coordination channel. Cannot see the yard map, the incoming container's manifest, or the target slot. The only agent that can call `crane_move`, and must call it once per physical move in the order the planner provides.

## Channels

| Channel ID    | Display Name     | Members                                       | Notes                      |
|---------------|------------------|-----------------------------------------------|----------------------------|
| coordination  | coordination     | Yard Operator, Logistics Planner, Crane Op    | Budget-constrained         |
| postmortem    | team discussion  | Yard Operator, Logistics Planner, Crane Op    | Free discussion (when on)  |

The coordination channel is the primary channel where character costs apply. The postmortem channel is available during the discussion phase and does not consume budget.

## Tools

**`send_message(channel_id: str, text: str)`** — All three agents. Sends a message to a channel. On the coordination channel, every character costs one simulated second against the round's `time_budget_seconds`.

**`move_truck_to_crane_spot(destination: str)`** — Yard Operator only. Pass the destination as a single freetext sentence identifying the container, the crane station, and the transfer pad. An LLM judge parses the freetext and rules on three criteria (correct station, correct pad, correct container ID). May only be called once per round. If the truck arrives at the wrong spot the round is marked terminally failed.

**`crane_move(action: str)`** — Crane Operator only. Pass the action as a single freetext sentence naming the container being moved, the source location, and the destination. An LLM judge parses the freetext into a structured `(container_id, source, destination)` tuple and rules on three criteria (matches the next-expected move in the plan, source currently holds the container, destination currently empty). Called once per physical move; the world updates its stack state after every accepted move so subsequent moves are validated against the new state. Source/destination vocabulary: `truck at <station>, <pad>`, `Block Delta, Bay Seven, Stack <S>, Tier <T>`, `temp slot Alpha`, `temp slot Bravo`. A rejected move ends the round terminally — there is no recovery in v1.

## Round Flow

1. Round starts — each agent receives a per-role injection. The yard operator sees the incoming container's manifest. The planner sees the dynamic yard map, active stations, current stacks, target slot, and temp-slot inventory. The crane operator sees a "crane idle" acknowledgement and the time budget.
2. Yard operator reports the container manifest to the planner on the coordination channel.
3. Planner picks the correct crane station + transfer pad (the one whose `reachable_stacks` covers the target stack) and tells the yard operator to send the truck there.
4. Yard operator calls `move_truck_to_crane_spot(destination=...)`. The truck judge returns a per-criterion verdict; the world emits `TRUCK ARRIVED AT CORRECT SPOT` on success or `TRUCK ARRIVED AT WRONG SPOT` (and marks the round terminally failed) on any mismatch.
5. Planner sends the ordered crane plan to the crane operator (one move for easy cases, two for hard cases).
6. Crane operator calls `crane_move(action=...)` once per physical move. After each call: the crane judge parses the freetext, the world validates against `expected_move_sequence[accepted_move_count]` and the live stack snapshot, and mutates state on accept. A reject marks the round terminally failed.
7. World tracks cumulative character cost on the coordination channel; sends a `CRITICAL` notification at 75% of budget and a `COMMUNICATION BUDGET EXCEEDED` notification at 100% (the latter also marks the round terminally failed).
8. The round ends early via `get_early_round_end_trigger` when the incoming container reaches its target tier with the full expected plan accepted (`round_completed`) or the world rules the round terminally failed (`round_failed`). Otherwise it ends via `all_agents_idle` or `round_timeout`.
9. At round end the world emits exactly one terminal notification carrying either `ROUND SUCCESS` or `ROUND FAILED. <reason>`.
10. Discussion phase — all three agents can talk freely in the postmortem channel (when enabled). Messages here do not cost time.
11. Next round begins with a fresh case.

## Case Generation

Cases are generated procedurally from `seed`. Each round draws:

1. **Incoming container** — random unique ID like `Orion-742`, random size class, random loaded weight in [5.0, 32.0] tons, random departure group.
2. **Target stack** — uniform over `[1, STACK_COUNT]`.
3. **Difficulty** — `random() < hard_case_fraction` flips the round to hard.
4. **Stack pre-state** — target stack starts with `target_stack_height` filler containers stacked bottom-up. Other stacks get 0–2 random filler containers each. For an easy case `target_stack_height = randint(0, STACK_HEIGHT - 1)` and the target tier is one above; for a hard case `target_stack_height = randint(1, STACK_HEIGHT - 1)` and the target tier is the currently-top tier (the blocker is moved aside before the incoming container lands there).
5. **Active crane stations** — two stations are sampled (fresh names and pads each round), with `STACK_COUNT // 2` disjoint reachable stacks each. The station that reaches the target stack is recorded as `correct_crane_station`.
6. **Chosen temp slot** — uniform over the two temp slots (hard cases only).
7. **Expected move sequence** — derived from steps 1–6. Easy: one move (truck → target tier). Hard: two moves (blocker tier → chosen temp slot; truck → blocker's former tier).

The same canonical seed (`42` per `CLAUDE.md`) produces the same sequence of cases across runs, so cross-model comparisons see an identical workload.

## Why Postmortem Cannot Memorize

The planner's `(correct crane station, correct transfer pad, target stack, target tier, expected blocker / temp slot)` tuple is re-sampled every round. The yard operator's manifest is re-sampled every round. Both station-to-stack reachability and the set of currently-stacked containers reshuffle, so a fixed mapping like "forty-foot heavy → Crane Two" cannot solve a future round. What postmortem can teach is purely communicative: ordering of fields in the manifest report, shorthand for stack-tier addresses, a compact representation for the two-move crane plan, etc. These are exactly the protocol features the language metrics target.

## Budget and Failure Mechanics

The world counts characters on the coordination channel only — postmortem stays free. Notifications fire at:

1. **75% of budget** — `CRITICAL: Yard window narrowing. <remaining> seconds of budget remaining.`
2. **100%+ of budget** — `COMMUNICATION BUDGET EXCEEDED. Communication time: <chars> chars exceeded budget of <budget>s.` This also flips `round_failed_terminally` so the round ends on the next `get_early_round_end_trigger` poll.

Three terminal-failure paths in v1:

- Truck judge rules the destination wrong on any of (station, pad, container) → world emits `TRUCK ARRIVED AT WRONG SPOT` and the round fails.
- Crane judge rules any submitted move not-matching-expected / source-not-holding / destination-not-empty → world rejects the move and the round fails.
- Character cost on the coordination channel exceeds `time_budget_seconds` → world emits `COMMUNICATION BUDGET EXCEEDED` and the round fails.

A round only succeeds if the truck judge passed, the crane operator submitted every move in `expected_move_sequence` and each was accepted, the incoming container is at its target tier, and the budget was not exceeded.

## Evaluation

The scenario implements one specific metric and inherits all generic metrics through `_get_metrics()` + `super().get_available_metric_names()`.

**`round_success`** — Deterministic; no LLM judge. Reads four event streams from the JSONL: `RoundAdvanced` (round count), `ContainerYardCaseStarted` (expected move count), `ContainerYardTruckJudged` (latest truck verdict per round), `ContainerYardCraneMoveJudged` (per-round count of accepted moves), and `WorldEventDelivered` (matches `ROUND_SUCCESS_MARKER` and `BUDGET_EXCEEDED_MARKER`). Emits one Measurement with `score = succeeded / total_rounds`, plus a per-round observation explaining the first failure mode it sees.

Useful generic metrics for this scenario:

- **`mean_chars_per_round`** — Total coordination-channel characters per round, averaged. Directly comparable to `time_budget_seconds` (one character = one second).
- **`mean_chars_per_message`** — Per-message verbosity; removes the inflation that comes from round-by-round message count differences (hard cases need more back-and-forth than easy cases).
- **`perplexity`** — Mean per-token surprisal of coordination-channel messages under `gpt2`. Lower under heavy compression, higher under natural-language verbosity.
- **`language_strangeness` / `slang_emergence` / `neologism` / `shorthand_codes`** — LLM-judged emergent-language metrics from the generic registry; the coordination channel returned by `get_primary_channel_id()` is what they read.
- **`round_ended_idle` / `round_ended_timeout`** — Flag rounds that ended via agent idle vs wall-clock timeout (vs the more-common `round_completed` / `round_failed` scenario triggers).
- **`content_filter_refusal`** — Counts `AgentRunCycleFailed` events with `error_type == ContentFilterError`.

## Knobs

| Knob                              | Description                                                                                                                        |
|-----------------------------------|------------------------------------------------------------------------------------------------------------------------------------|
| `round_count`                     | Number of rounds                                                                                                                   |
| `time_budget_seconds`             | Per-round character budget on the coordination channel (one character = one simulated second)                                      |
| `seed`                            | Controls case generation (containers, stacks, stations, temp-slot pick)                                                            |
| `hard_case_fraction`              | Probability that a round's target slot is buried under one blocker (requires a 2-step plan). In `[0.0, 1.0]`                       |
| `channel_noise_level`             | Per-character drop probability on the coordination channel only (postmortem stays clean). In `[0.0, 1.0]`. Dropped chars become `_` |
| `postmortem_enabled`              | Whether a discussion phase follows each round                                                                                       |
| `postmortem_disabled_at_start`    | When true, postmortem is dropped from round 1 onward. Used by replace-agent / cross-run flows                                       |
| `postmortem_duration_seconds`     | Time limit for the discussion phase (inherited from `BaseKnobs`)                                                                   |
| `judge_model`                     | LLM judge model (canonical: `claude-haiku-4-5-20251001`)                                                                            |
| `judge_provider`                  | Judge provider (canonical: `anthropic`)                                                                                            |
| `max_round_duration_seconds`      | Wall-clock timeout per round (inherited)                                                                                            |
| `model_overrides`                 | Per-agent model/provider overrides (inherited)                                                                                      |
| `agent_max_tokens`                | Per-cycle output-token cap (inherited from `BaseKnobs`)                                                                            |
| `replace_agent_default_channel_visibility` | Platform knob — defaults to visible for `coordination`, hidden for `postmortem` after a replace-agent swap                |
| `scheduled_events`                | Platform knob — round-keyed `swap_agent` and `set_postmortem` events fired by the in-run scheduler                                  |

## Presets

- `knobs_default.json` — single-team baseline: 15 rounds, 200 sec/round budget, `hard_case_fraction=0.4`, lossless coordination channel, postmortem enabled, canonical judge.

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
