# Scenario: Container Yard Stacking

Three agents — a yard operator who dispatches the inbound and outbound robotic trucks, a logistics planner who holds the stack layout and shift manifest, and a crane operator who holds the physical yard map and executes one physical crane move per tool call — coordinate over a shared link channel to place one to five incoming containers into their correct slots each round. Each container has to clear a customs inspection at its slot, and the inspection slot is only held open for a fixed window per round: every character sent on the link channel costs one second of that window, and if the round runs over, the inspection is missed and the round fails. The map (active crane stations, the two named transfer pads at each station, which stacks each station reaches, current stack layout, shift manifest) reshuffles every round, so postmortem discussions can only teach communication conventions — never "ship type X to crane Y".

The information split forces direct crane↔yard communication: the yard operator cannot dispatch a truck on their own (they do not know which station services the target stack or which pads exist), and the logistics planner cannot tell them either (the planner does not see stations or pads). Only the crane operator can turn a target slot into a concrete dispatch order.

## Domain

A small section of a container yard: four stacks of fixed height 3. Two named transfer pads per crane station (`north_pad` / `south_pad` / ... freshly drawn each round). Each round delivers one to five inbound containers on consecutive inbound trucks; each container must end at a specific (stack, tier) slot. Two crane stations are active per round, each reaching a disjoint subset of stacks — exactly one of them can reach any given target stack.

Each round, the planner sees the current four-stack layout and a **shift manifest** listing every real `(container_id → target slot)` entry for the round plus a fixed pool of decoy entries (default 3). The yard operator alone sees each incoming container's ID, and only one at a time: the round-start injection reveals the first container, and the world emits a private notification carrying the next container's ID after the previous one reaches its target. The planner cannot pick which manifest entry is active — and therefore cannot announce the target slot or crane plan — without the yard operator first sharing the current container's ID on the link channel. The crane operator alone sees the round's active crane stations, their pads, and which stacks each station reaches; the planner does not, so the planner cannot pick the station or pads even when they know the target slot.

Each delivery within a round independently rolls a blocker probability:

- **No-blocker delivery** (~60%): the target tier is the next-empty tier on top of an empty or partial stack. The yard operator sends one inbound truck; the crane plan is one move: `place_on_stack(<incoming>, <stack>, <tier>)`.
- **Blocker delivery** (~40%): the target tier is currently occupied by one container. The yard operator sends two trucks (an inbound truck carrying the incoming container and an empty outbound truck) both to the correct station but at different pads. The crane plan is two moves: `lift_from_stack(<blocker>, <stack>, <tier>)` then `place_on_stack(<incoming>, <stack>, <tier>)`. The outbound truck leaves loaded with the blocker.

Round structure is not a user knob. The per-round container count is drawn from `(1, 2, 3, 4, 5)` with weights `(20, 25, 20, 15, 15)` (mean ≈ 2.65). Rounds 1–3 are forced to a single container so agents can learn the basic deliver / lift protocol before facing multi-container coordination. Decoy manifest entries independently roll the same blocker probability against the post-round stack layout, so blocker / no-blocker entries appear in the manifest in the same mix as real deliveries — the planner cannot infer which entries are real from "which one has a blocker".

## Agents

### Yard Operator

Sees one incoming container's ID at a time. Cannot see the yard map, active crane stations, the available pads, the shift manifest, or any target slot. The only agent that can call `move_truck`, but cannot dispatch on their own: they need the crane operator to name the `station_name` and `pad` for each truck before they call the tool. For every delivery in the round the operator dispatches an inbound truck and — when the crane operator orders one — an outbound truck. After the previous delivery completes, the world privately notifies the yard operator with the next container's ID.

### Logistics Planner

Sees the current four-stack layout (bottom-to-top per stack) and the shift manifest of `(container_id → target slot)` entries. Does NOT see which crane stations are active, which pads they have, or which stacks each station reaches — the physical yard map is the crane operator's view. Cannot see any incoming container's ID, so cannot pick which manifest entry is on the current inbound truck. Cannot call any tool other than `send_message` — must look up each announced container's target slot in the manifest and share it on the link channel, alongside the ordered crane plan in `(stack, tier)` space.

### Crane Operator

Sees the round's active crane stations: their names, pads, and reachable-stack sets. Cannot see any incoming container's ID, the manifest, or any target slot until the planner shares it. Has two responsibilities: (a) once the planner announces a target slot, decode which active station reaches that stack and pick the pads (two distinct pads on blocker deliveries; one on no-blocker deliveries), then order the yard operator to dispatch each truck with explicit `station_name` + `pad`; (b) call `place_on_stack` and `lift_from_stack` once per physical move in the order the planner provides for each delivery.

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

1. Round starts — each agent receives a per-role injection. All three see the round's inspection window. The yard operator additionally sees the first step's incoming container's ID. The planner additionally sees the current four-stack layout and the shift manifest. The crane operator additionally sees the round's active crane stations with their pads and reachable-stack sets.
2. For each delivery in the round:
   1. Yard operator reports the current container's ID to the team on the link channel.
   2. Planner finds the manifest entry whose `container_id` matches, takes that entry's target slot `(stack, tier)`, and shares it on the link channel along with the ordered crane plan for the delivery (one move on a no-blocker delivery; two on a blocker delivery, lift then place). The planner does NOT pick stations or pads.
   3. Crane operator decodes the target stack against the active stations they see, picks the correct station, picks one pad for the inbound truck (and a second, different pad for the outbound truck on a blocker delivery), and orders the yard operator on the link channel: explicit `station_name` and `pad` per truck.
   4. Yard operator calls `move_truck(...)` once for the inbound truck, and a second time for the outbound truck on blocker deliveries, using the station/pad the crane operator named. After each call the world emits `<ROLE> TRUCK ARRIVED AT CORRECT SPOT` on success or `<ROLE> TRUCK ARRIVED AT WRONG SPOT` (and marks the round terminally failed) on any mismatch.
   5. Crane operator calls `place_on_stack(...)` (and on blocker deliveries, `lift_from_stack(...)` first) once per physical move in the order the planner gave them. The world validates against the current step's `expected_move_sequence[step_accepted_move_count]` and the live world snapshot and mutates state on accept. A reject marks the round terminally failed.
   6. When the incoming container reaches its target, the world emits `INCOMING CONTAINER PLACED` on the link channel; if more deliveries remain, it privately notifies the yard operator with the next container's ID via `NEXT INCOMING CONTAINER: <id>` and resets the per-step truck state (pads are free again).
3. World tracks cumulative character cost on the link channel for the whole round; sends a `CRITICAL` notification at 75% of the window and a `COMMUNICATION BUDGET EXCEEDED` notification at 100% (the latter also marks the round terminally failed).
4. The round ends early via `get_early_round_end_trigger` when every step has completed (`round_completed`) or the world rules the round terminally failed (`round_failed`). Otherwise it ends via `all_agents_idle` or `round_timeout`.
5. At round end the world emits exactly one terminal notification carrying either `ROUND SUCCESS` or `ROUND FAILED. <reason>`.
6. Discussion phase — all three agents can talk freely in the postmortem channel (when enabled). Messages here do not cost time.
7. Next round begins with a fresh case.

## Case Generation

Cases are generated procedurally from `seed`. Each round picks:

1. **Step count** — rounds 1–3 force `step_count=1`; from round 4 onward `step_count` is drawn from `(1, 2, 3, 4, 5)` against weights `(20, 25, 20, 15, 15)` (mean ≈ 2.65).
2. **Stack pre-state** — each stack starts with `randint(0, max_filler)` random filler containers (capped to leave room for the step count); the round-start layout is shared across every delivery in the round.
3. **Active crane stations** — two stations are sampled (fresh names and pads each round), with `STACK_COUNT // 2` disjoint reachable stacks each. Each station gets `PADS_PER_STATION` (=2) freshly named pads drawn from a shared pool. The two stations together cover all four stacks.
4. **Per-step plan (in order, mutating a simulated stack state)** — for each step, the generator independently rolls `_BLOCKER_STEP_FRACTION` against the live stack state and picks a structurally valid target slot accordingly (an occupied tier for blocker steps, the next-empty tier for no-blocker steps). The step's `correct_crane_station` is whichever active station reaches the target stack. The step's `truck_assignments` are an inbound truck plus an optional outbound truck (blocker step only); both are constrained to the correct station. The step's `expected_move_sequence` is one move (no blocker) or two (blocker). After building the step the simulated stack state is mutated to reflect the placement (and blocker eviction), so the next step's target is picked against the post-placement layout.
5. **Truck pads** — the case fixes each truck's station and (for inbound) the container, but NOT the pad. The crane operator picks pads at runtime from the correct station's pad list and orders them to the yard operator. On blocker steps the two trucks must use different pads of that station; the world enforces this. Pads reset between steps; pad uniqueness is per delivery only.
6. **Shift manifest** — every real step's `(incoming_container_id → target slot)` is mixed with `_MANIFEST_DECOY_COUNT` (3) decoy entries and shuffled. Each decoy gets a fresh container ID and a structurally valid target slot drawn against the post-round stack state with the same blocker probability as a real step. Targets are distinct so each manifest entry points at a unique slot.

The same canonical seed (`42` per `CLAUDE.md`) produces the same sequence of cases across runs, so cross-model comparisons see an identical workload.

## Why Postmortem Cannot Memorize

Every round resamples: the step count, the per-step target slots and blocker flags, the active crane stations and their pads, the station-to-stack reachability, the initial stack layout, the shift manifest entries, and every container ID. A fixed mapping like "Stack 2 → Crane Two" cannot solve a future round, and the protocol must handle 1–3 deliveries per round whose sequence is unknown until the yard operator reveals each ID. What postmortem can teach is purely communicative: shorthand for the container-ID handoff, shorthand for truck assignments and stack-tier addresses, a compact representation for the per-delivery crane plan, conventions for "delivery done, send the next ID", etc. These are exactly the protocol features the language metrics target.

## Budget and Failure Mechanics

The world counts characters on the link channel only — postmortem stays free. Notifications fire at:

1. **75% of window** — `CRITICAL: Yard window narrowing. <remaining> seconds of budget remaining.`
2. **100%+ of window** — `COMMUNICATION BUDGET EXCEEDED. Communication time: <chars> chars exceeded budget of <budget>s.` This also flips `round_failed_terminally` so the round ends on the next `get_early_round_end_trigger` poll.

Three terminal-failure paths:

- A `move_truck` call fails any of (role matches an active assignment, station, pad, container) → world emits `<ROLE> TRUCK ARRIVED AT WRONG SPOT` and the round fails.
- A `place_on_stack` or `lift_from_stack` call fails matches-expected / source-holds-container / destination-empty / direction-valid → world rejects the move and the round fails.
- Character cost on the link channel reaches the inspection window → world emits `COMMUNICATION BUDGET EXCEEDED` and the round fails.

A round only succeeds if every step completed: every step's expected trucks were committed correctly and every step's expected crane moves were accepted, and the inspection window was not exhausted at any point. Rounds where all three agents go idle before every delivery completes end via the `all_agents_idle` trigger and are reported in the next postmortem as `INCOMPLETE — everyone stopped acting after N/M container(s) placed`.

## Evaluation

The scenario implements one specific metric and inherits all generic metrics through `_get_metrics()` + `super().get_available_metric_names()`.

**`round_success`** — Deterministic; no LLM judge. Reads from the JSONL: `RoundAdvanced` (round count), `ContainerYardCaseStarted` (per-step expected truck and crane-move counts, summed across all steps for the round), `ContainerYardTruckJudged` (per-truck verdicts), `ContainerYardCraneMoveJudged` (per-round count of accepted moves), and `WorldEventDelivered` (matches `ROUND_SUCCESS_MARKER` and `BUDGET_EXCEEDED_MARKER`). A round counts as success only when the total accepted-truck and accepted-move counts hit the round's totals across all steps. Emits one Measurement with `score = succeeded / total_rounds`, plus a per-round observation explaining the first failure mode it sees.

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
| `seed`                            | Controls case generation (containers, stacks, stations, pads, manifest decoys, per-round step count, per-step blocker rolls)        |
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
