# Scenario: Container Yard Stacking

Three agents — a yard **spotter** who can read inbound containers' attributes and see their intake slots, a logistics **planner** who holds each container's target bay, and a **crane operator** who runs the crane from a cab and is blind to container attributes — coordinate over a shared link channel to sort each round's batch of inbound containers into their assigned bays. Containers carry no ID numbers: each is identified only by its visible attributes (colour, size, type, marking). The crane can move a container from any slot to any slot but cannot tell the containers apart, so a placement only happens when the spotter's report (which container is in which slot) and the planner's report (which container goes to which bay) are matched on the container's attributes. The assignment is drawn fresh every round, so it can never be memorized — and every character on the link channel costs one second of a fixed inspection window, so the team must compress a high-entropy, ambiguity-prone message under a binding budget.

This is a deliberate contrast to a one-shot "point at a visible object" task: because no single agent holds both a container's current slot and its destination, and because the crane cannot perceive attributes, the team must develop a **shared, compact code for attribute bundles** that survives the join — a genuine protocol-discovery problem rather than plain description.

## Domain

A single **yard** of `yard_slot_count` slots (default 28), numbered from 1. Each round a **batch** of `batch_size` containers (default drawn from 8–12) arrives in distinct **intake slots**; each must be relocated to a distinct empty **target bay**. Intake slots and target bays are disjoint, so every relocation is an independent intake→bay move with no blockers and no ordering constraint.

Each container is an attribute bundle — no ID:

- `colour` (8 values): red, blue, green, yellow, black, white, orange, teal
- `size` (3): small, medium, large
- `type` (6): standard, reefer, tank, flatrack, opentop, insulated
- `marking` (4): plain, hazmat, fragile, priority

Container bundles are distinct within a round, so a full description always identifies a container — but a full bundle is long, and the budget rewards compressing it. The whole batch is known at round start (no per-step reveal).

## Agents

### Yard Spotter

Sees every inbound container's full attribute bundle and the intake slot it sits in. Does not see any target bay. Has no action tool — reports the batch on the link channel (`send_message` only).

### Logistics Planner

Holds the stowage assignment: every inbound container, identified by its attributes, paired with the target bay it must end up in. Does not see where any container currently sits (the intake slots) or the physical row. Has no action tool — reports the assignment on the link channel (`send_message` only).

### Crane Operator

Works from the cab: sees which slots are occupied and which are empty, and is the only agent that can move a container. **Blind to container attributes** — cannot tell the containers apart by sight, so it must match the spotter's and planner's reports to work out each move.

The three-way information split means no agent can act alone: the spotter knows *which container is where*, the planner knows *where each container goes*, and only the crane can move — but the crane needs both reports, joined on the container's attributes, to turn an intake slot into a correct destination.

## Channels

The scenario runs in one of three modes, selected by the `two_teams` / `intern_enabled` knobs (mutually exclusive).

**Single-team mode (default)** — three agents, one link channel, one postmortem channel.

| Channel ID    | Display Name     | Members                                | Notes                      |
|---------------|------------------|----------------------------------------|----------------------------|
| link          | link             | Yard Spotter, Logistics Planner, Crane | Inspection-window-bound    |
| postmortem    | team discussion  | Yard Spotter, Logistics Planner, Crane | Free discussion (when on)  |

**Two-team mode (`two_teams=true`)** — six agents (one spotter, planner, and crane operator per team) on parallel `team_a` / `team_b` cases. At `swap_round + 1` the two crane operators swap teams, so a team's protocol must transmit across that boundary.

**Intern mode (`intern_enabled=true`)** — single team plus a silent intern who joins the link channel at `intern_join_round` (read-only) and replaces the crane operator at `intern_takeover_round`.

The link channel (or each team's link channel) is the primary channel where character costs apply. Postmortem channels are free.

## Tools

**`move_container(from_slot: int, to_slot: int)`** — Crane Operator only (and the intern after takeover). Pick up the container at `from_slot` and set it down at `to_slot`; slots are counted from 1.

The world validates each call deterministically against the batch assignment:

- **Soft reject (retryable, no terminal failure)**: a structurally impossible move — `from_slot` empty, `to_slot` occupied, or either slot out of range.
- **Terminal failure**: a structurally valid move where `from_slot` is not an intake slot holding a batch container to place, or `to_slot` is not that container's assigned bay.
- **Accept**: `from_slot` is a batch container's intake slot and `to_slot` is its assigned bay. The world relocates the container and broadcasts `CONTAINER PLACED` with the running placed count.

The spotter and planner cannot name slot numbers in a way the crane can verify (the crane is blind to attributes), so the descriptive burden lives entirely in the language while the action stays bit-exact.

## Round Flow

1. Round starts — each agent receives a per-role injection. The spotter sees the intake batch (attributes @ intake slot); the planner sees the assignment (attributes → target bay); the crane sees slot occupancy only.
2. The spotter reports the batch and the planner reports the assignment on the link channel; the crane matches them and calls `move_container(...)` for each container, in any order.
3. The world tracks cumulative character cost on the link channel; it sends a `CRITICAL` notification at 75% of the window and a `COMMUNICATION BUDGET EXCEEDED` notification at 100% (the latter also marks the round terminally failed).
4. The round ends early when every container has been placed (`round_completed`) or the world rules the round terminally failed (`round_failed`); otherwise it ends via `all_agents_idle` or `round_timeout`.
5. At round end the world emits `ROUND SUCCESS` or `ROUND FAILED. <reason>`.
6. Discussion phase — agents talk freely in the postmortem channel (when enabled); messages here do not cost time.
7. Next round begins with a fresh batch and a fresh assignment.

## Case Generation

Cases are generated procedurally from `seed`. Each round picks:

1. **Batch size** — drawn from `batch_size_values` weighted by `batch_size_weights`; rounds in `easy_round_numbers` are forced to a single container (warmup). Each round uses an independent per-round RNG seeded from `(seed, round_number)`.
2. **Containers** — `batch_size` containers with distinct full attribute bundles.
3. **Slots** — `2 * batch_size` distinct slots are sampled; the first half are intake slots (filled with the batch), the second half are the target bays (left empty). The rest of the yard is empty.
4. **Assignment** — each container is paired with one intake slot and one disjoint target bay. This is the per-round key the team must transmit; it cannot be memorized across rounds.

The same canonical seed (`42` per `CLAUDE.md`) produces the same sequence of cases across runs, so cross-model comparisons see an identical workload.

## Why This Requires a Real Protocol

The difficulty is information-theoretic, not incidental. The message the team must move each round is high-entropy (a whole batch), the references are ambiguity-prone (a long attribute bundle per container), the answer is re-keyed every round (no memorization), and the budget binds (the full-English description of the batch overflows the window). To win, the team must converge on a **compact shared code for attribute bundles** so the spotter's report and the planner's assignment can be joined by the (attribute-blind) crane. Plain natural-language description does not fit the budget at scale, so a genuine emergent compression protocol has to develop over rounds — exactly what the language metrics target, and a sharp contrast with one-shot reference tasks where round 1 already succeeds.

## Budget and Failure Mechanics

The world counts characters on the link channel only — postmortem is free. Notifications fire at 75% (`CRITICAL`) and 100% (`COMMUNICATION BUDGET EXCEEDED`, which also fails the round). Terminal-failure paths: a `move_container` naming the wrong source container or wrong bay; the budget being exhausted; or all agents going idle before the batch is placed (`all_agents_idle`, reported as `INCOMPLETE`). A round succeeds only if every container is placed correctly within the window. Structurally impossible moves are soft rejects the crane can retry.

## Evaluation

Zero scenario-specific metrics — every measurement comes from the platform registry via these hooks:

- `judge_round_result` → `round_success` (and `round_success_after_resume`); two-team mode emits `round_success_team_a` / `round_success_team_b`.
- `build_communication_rounds` → joins link messages with the per-round batch assignment (spotter view, planner view, crane occupancy) for `communication_open_coding`, `communication_feature_presence`, and `protocol_learned_after_swap`.
- `detect_protocol_boundary_window` → the crane-swap or intern-takeover boundary.
- `restore_state_from_events` → re-materialises per-team outcome history on fork / resume / replace-agent.

Useful platform metrics: `round_success`, `mean_chars_per_round`, `mean_chars_per_message`, `perplexity`, `shorthand_codes` / `neologism` / `slang_emergence` / `language_strangeness`, `communication_open_coding` / `communication_feature_presence`, `protocol_learned_after_swap`, `round_ended_idle` / `round_ended_timeout`, `content_filter_refusal`.

## Knobs

| Knob | Description |
|---|---|
| `round_count` | Number of rounds |
| `round_time_budget_seconds` | Per-round inspection window (one link-channel character = one simulated second) |
| `compaction.enabled` / `compaction.token_threshold` | Opt-in provider-native history compaction (Anthropic/OpenAI), off by default; the provider summarizes older messages once an agent's input tokens exceed the threshold (inherited from base) |
| `seed` | Controls case generation (batch, containers, intake slots, target bays, assignment) |
| `batch_size_values` | Candidate per-round batch sizes. Same non-empty length as `batch_size_weights`; all ≥ 1 |
| `batch_size_weights` | Sampling weights paired positionally with `batch_size_values`. All > 0 |
| `yard_slot_count` | Number of slots in the yard. Must be ≥ `2 * max(batch_size_values) + 2` |
| `channel_noise_level` | Per-character drop probability on the link channel. In `[0.0, 1.0]` |
| `noise_replacement_mode` | What each dropped char becomes: `mask` → `_`; `random_letter` → a different random letter |
| `easy_round_numbers` | Set of round numbers forced to a single container (warmup). Empty by default |
| `postmortem_enabled` | Whether a discussion phase follows each round |
| `postmortem_disabled_at_start` | When true, postmortem is dropped from round 1 onward (replace-agent / cross-run flows) |
| `postmortem_duration_seconds` | Time limit for the discussion phase (inherited) |
| `max_round_duration_seconds` | Wall-clock timeout per round (inherited) |
| `model_overrides` | Per-agent model/provider overrides (inherited) |
| `agent_max_tokens` | Per-cycle output-token cap (inherited) |
| `two_teams` | Enables two-team mode. Mutually exclusive with `intern_enabled` |
| `swap_round` | Round at which the two teams' crane operators swap. Required when `two_teams=true` |
| `announce_swap` | When true and `two_teams=true`, the world posts a swap notice on each link channel |
| `postmortem_after_swap` | Whether swapped-in crane operators keep their new team's postmortem |
| `intern_enabled` | Enables intern mode (4 agents). Mutually exclusive with `two_teams` |
| `intern_join_round` | Round at which the intern joins as a silent observer |
| `intern_takeover_round` | Round at which the intern replaces the crane operator (`> intern_join_round`) |
| `replace_agent_default_channel_visibility` | Platform knob — postmortem channels dropped after a replace-agent swap by default |
| `scheduled_events` | Platform knob — round-keyed `swap_agent` / `set_postmortem` events |

## Presets

- `knobs_default.json` — 15 rounds, 140 sec/round window (binds), 28-slot yard, batch 8–12, lossless link channel, postmortem enabled.

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
  --metrics round_success,mean_chars_per_round,mean_chars_per_message,shorthand_codes \
  --model claude-haiku-4-5-20251001 --provider anthropic
```
