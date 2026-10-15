# signal_game

Two players each move a figure on their own small grid of coloured squares. Each
sees its own grid's colours, the square the partner stands on, and every move the
partner makes. A round scores when both finish on squares of the same colour. There
is no channel and no tool that takes text, so whatever one player tells the other
has to be built out of moves that also serve to reach a square.

This is the Embodied Communication Game of Scott-Phillips, Kirby & Ritchie (2009),
adapted for two LLM agents. It asks the question that paper asked of people: can a
player make a move read as a signal, when nothing marks any move as one? The paper's
participants did it by moving in ways that made no sense as travel, such as
oscillating along one side of the box. `excess_moves` counts that behaviour.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run signal_game \
  --model claude-haiku-4-5-20251001 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  > ./runs/signal_game_stdout.log 2>&1 &
```

## The game

Each round draws two grids of `grid_size` × `grid_size` squares, one per player,
each square coloured independently from the first `colour_count` colours of red,
blue, green, yellow, purple, orange. A colour can repeat on a grid or be missing
from it. A pair of grids sharing no colour is drawn again, so every round can be won,
as the paper also guarantees ("at least one of the four colours will appear in both
players' boxes").
Grids come from `seed` and are the same in every run with that seed.

Both figures start every round on row 1, col 1. A player has `moves_per_round` moves:
`up`, `down`, `left` and `right` each spend one. One `move` call takes a list of 1 to
10 of them (`MAX_MOVES_PER_CALL`) and applies them in order. The tool schema carries
both bounds and the four directions, so a call breaking them is refused before it
reaches the scenario and moves nothing. A step off the grid, or past the player's last
move, stops the list there: the steps before it stand, and the refused step spends
nothing and is not shown to the partner. A player finishes by calling
`read_notifications(wait_for="next_round")`, which fixes its square for the round.

The round ends when both players have finished, each having waited for the next round
or spent every move (trigger `both_finished`), or after `max_round_duration_seconds`.
It succeeds when the colours under the two figures match. Scoring is deterministic,
with no judge.

The next round's briefing reports the result, both final colours, and the partner's
whole grid, which is how a player learns what the partner was looking at.

### Turns

Under `turn_based` the players alternate. Whoever calls `move` first takes the round's
first turn; after that each `move` call is one turn, and a player that has moved waits
for its partner's turn before moving again. A move out of turn is refused and spends
nothing. On its own turn, a plain `read_notifications()` passes the turn to the partner,
who sees it as `waited for notification`. A pass answering a pass wakes no one, so both
players are parked and the round ends `all_agents_waiting`. A player may finish at any
time, and once its partner has finished it moves without waiting for turns.

A move made while the player has partner actions it has not been shown is refused, with
those actions in the refusal. Two calls can arrive together at the start of a round, or
a call drafted during the partner's turn can land after it: either way, every accepted
move follows what its player saw.

## What a player sees

The briefing gives the player its own grid (and the partner's, under
`partner_colours_visible`). Every `move` result, and every wake, carries the board:

```
You moved (your action 2): [right] -> row 1, col 2.
Round 2. You are on row 1, col 2 (red), 197 move(s) left.
Your partner is on row 2, col 1.
Your partner's actions since you last looked, numbered by your partner's actions this round:
  1 - [down, right, left] -> row 2, col 1
  2 - waited for notification
It is your partner's turn. read_notifications() waits for it.
```

Each action is one call: a `move` with its directions and the square it ended on, a
passed turn, or `finished the round`. The number counts that player's own actions in
the round. Each partner action is shown exactly once. The last line appears only under
`turn_based`.

Every change to the round is applied synchronously, so one `move` call's steps land
together and nothing from the partner falls between them. A lock keeps the events in
the order the changes happened. Finishing and passing happen when a player parks, in
`on_agent_parked`, which is synchronous, so their events are logged by a task that
takes the same lock.

With `observe_enabled`, `observe()` returns the same board with every partner action of
the round rather than only the unseen ones. It spends no move and is not one of the
player's actions. It also marks those actions shown, so the next result lists only what
follows. While both players' last call was `observe`, each board says they are both
observing and that nothing changes until one of them moves.

## What a player is told

The system prompt follows the paper's instruction: another player moves the second
figure, sees the player's moves but not its colours, and the two score together.
"Coordinate with your partner." It does not say that moves can carry a message:
finding that out is what the game measures. The paper also gave participants "more
detailed instructions" after a practice period, without saying what they were, so the
wording beyond "coordinate" is this scenario's. Under `turn_based` a paragraph states
the turn rules.

## Tools

| Tool | What it does |
|---|---|
| `move(directions)` | 1 to 10 steps, each `up`, `down`, `left` or `right`, applied in order. Each step spends one move; returns the board. Under `turn_based`, one turn |
| `observe()` | Only under `observe_enabled`. The board with every partner action of the round; spends no move |
| `read_notifications()` | At startup and after a round changes, the briefing. Mid-round, waits until the partner acts and returns the board. Under `turn_based`, on the player's own turn, passes the turn |
| `read_notifications(wait_for="next_round")` | Finishes the player's round on its square and waits for the next briefing |

`hidden_base_tools` withholds `send_message`, `read_channel`, `list_channels` and
`get_channel_members`. The run has no channels, and `validate_outgoing_message`
refuses any message.

A resumed `read_notifications` returns a JSON wake package: `type` (`done` once the
game is over), `round`, `wake_reasons`, `briefings`, `board` and `notice`.

### Waiting

A plain `read_notifications()` has no default timeout. A partner's `move` call resumes
it once, after every step of the call has been applied, so a waiting player reads the
whole call at once. The resume goes through `release_wait`, with `partner_acted` among
the wake reasons, and a player that parks with partner actions it has not been shown is
resumed at once. A player waiting on a partner that has finished, or that is itself
waiting, would wait forever: it is released with a notice saying so, at most twice a
round. Past that it stays parked, and with both players parked the round ends
`all_agents_waiting` (`ends_round_when_all_agents_waiting`).

A move, or a finish, from a model request issued in an earlier round, or from a player
that has not read the current briefing, does not act on the round.

`allows_parallel_tool_calls()` returns False, so a model makes one tool call per
response. With parallel calls allowed, Claude Sonnet 5.5 sent `move` together with the
calls that fix its square and wait, before its partner could reply: in a five-round run
the runner refused 6 `read_notifications` calls for arriving alongside other calls. With
the setting off, a run of the same length had none.

## Knobs

`BaseKnobs` supplies `round_count`, `max_round_duration_seconds`, `model_overrides` and
the other platform knobs. The scenario adds:

| Knob | Meaning | `knobs_default` |
|---|---|---|
| `grid_size` | Squares per side, 2 to 5 | 2 |
| `colour_count` | Colours drawn from, at most the squares in a grid | 4 |
| `moves_per_round` | Moves per player per round, at most 1000 | 200 |
| `partner_colours_visible` | Show each player the partner's colours too | `false` |
| `observe_enabled` | Offer `observe` | `false` |
| `turn_based` | Players alternate turns | `false` |
| `seed` | The grids | 42 |

`knobs_default` also sets `round_count` 10 and `max_round_duration_seconds` 600. The
validator refuses `postmortem_enabled=true` (a debrief is a channel) and
`compaction.enabled=true` (the platform's compaction prompt talks about channels).

| Preset | Condition |
|---|---|
| `knobs_default` | As close to the paper's game as the platform allows |
| `knobs_shared_colours_control` | `partner_colours_visible=true`: no private information, so the round can be won by reasoning alone, with nothing to signal |

Run the control first. If players fail it, they fail the coordination itself, and the
default has nothing to be read against.

## Where this departs from the paper, and why

| The paper | Here | Why |
|---|---|---|
| Players move in real time, and each sees the other's figure move continuously | A `move` call is a burst of up to 10 steps, applied without the partner acting in between. The partner sees the call as one numbered action | Agents act in model cycles, not in time. A burst stands in for a quick run of key presses and the gap between calls for a pause, so a gesture such as an oscillation is not broken up by the partner's moves. Speed and simultaneity are still lost |
| Players move whenever they like | The same by default; under `turn_based` they alternate | Alternation guarantees each player sees the partner's last action before its next one |
| No move limit; play for a fixed session time (40 minutes). The paper reports no move counts | 200 moves per player per round, and `max_round_duration_seconds` per round | A model can loop on moves indefinitely, so a cap bounds cost. 200 is set high enough that it does not shape play: the best human pair's signals took at most five moves, and a round of signalling, travel and replies fits many times over |
| A round ends when both players stop | `read_notifications(wait_for="next_round")`, or spending every move | An agent has no "stopped moving" state without one; waiting for the next round is the stop |
| The partner's stopping is visible as the figure no longer moving | `finished the round` appears in the action list | The same information, stated |
| A player can look at the screen at any time without moving | Under `observe_enabled`, `observe` returns the round's partner actions without spending a move | Otherwise the only views are a move's result and a wait that ends when the partner acts |
| Start position: not stated in the paper | Both start on row 1, col 1 | A shared fixed start makes "shortest path to the final square" well defined for `excess_moves` |
| Grid 2 × 2, four colours | Defaults to the same; `grid_size` and `colour_count` are knobs | A larger grid gives more room for path shapes that read as signals |
| One condition (told to coordinate) | The same, plus a shared-colour control | The control is a baseline: it shows whether agents can coordinate when nothing needs signalling |

## Measurement

`round_success` reads the `RoundResultRecorded` events the game clock writes from
`judge_round_result`.

`excess_moves` is the scenario's own metric, in the registry's scenario-scoped list
and advertised only by this scenario. Per round and player, it is the moves made
minus the shortest path from the start to the square the player finished on: the
inefficiency measure of de Bie, Scott-Phillips, Kirby & Verheij (2010). A player that
walks straight to its square scores 0; every detour and back-and-forth adds 1.
`score` is the mean over player-rounds, `per_round[].value` the round's mean over the
two players with each player's move trace in the note, and `per_agent[].value` each
player's mean over rounds.

It does not tell intent from confusion: a player wandering because it is unsure
scores the same as one oscillating on purpose. Read it beside `round_success` and the
traces in the notes, and against the control.

`build_communication_rounds` renders each player's move trace as that round's message,
with both grids and the final squares as the ground truth, so
`communication_open_coding` and `communication_feature_presence` can read the traces.
`get_primary_channels()` is empty, so `perplexity`, `mean_chars_per_round`,
`mean_chars_per_message` and the language-emergence judges skip.

## Events

| Event | Holds |
|---|---|
| `signal_game_round_started` | Both grids, the start square, the move budget, whether colours are shared |
| `signal_game_move_made` | Player, direction, from and to squares, sequence number, moves used |
| `signal_game_turn_passed` | Under `turn_based`, the player that passed, its action number, its square |
| `signal_game_player_finished` | Player, final square and colour, moves used |
| `signal_game_round_resolved` | Final squares and colours, moves used, success, trigger |

`restore_state_from_events` seeds resolved rounds, so the first briefing after a fork
at a round boundary reports the previous result. Resuming mid-round is not supported:
positions and the action log of an open round are not rebuilt.

## Files

| File | Holds |
|---|---|
| `ids.py` | Agent ids, tool and trigger names, the palette, `Direction`, `TurnKind`, `TurnState` |
| `knobs.py`, `knobs_*.json` | Knobs, validator, presets |
| `board.py` | Squares, moves, shortest paths, grid generation |
| `world.py` | Positions, moves used, the turn, the round's action log with each player's read position, outcomes |
| `turn_events.py` | The events one logged action produces |
| `events.py` | The events above |
| `wake_package.py` | The wake package `read_notifications` returns |
| `scenario.py` | Agents, tools, briefings, board view, waiting and release, round end, verdict |
| `prompts/` | System prompt, briefing, board view, move result, refusals, release notice, runner prompts, `description.jinja` |
| `evaluation/excess_moves_metric.py` | The metric above |
| `evaluation/build_communication_rounds.py` | The move-trace views |

There is no `team_declaration.py`: `TeamSpec` requires a task channel, so agents are
built in `scenario.py`, as dead_drop and prisoners_dilemma do. The decision baseline in
`tests/engine/test_scenario_decisions_unchanged.py` leaves signal_game out, because
its harness drives agents by chatting on a primary channel. `tests/scenarios/signal_game/`
plays the round loop with scripted moves instead, and `test_tools_direct.py` there calls
`move` and `observe` directly to pin event order, the turn refusals and what `observe`
shows;
`tests/metrics/test_excess_moves.py` covers the metric.

## Known limitations

- The last round's result is never shown to the players. Each result reaches them in
  the next round's briefing, and after the final round there is none, so the
  end-of-run wake carries no outcome. Scoring is unaffected.
- A round can end on `all_agents_idle` while both players wait with
  `read_notifications(timeout_s=...)`. The game clock measures quiet time from the
  last channel message and this scenario sends none, so once both players are parked
  the idle check ends the round before either timer fires.
- Resuming mid-round is not supported: an open round's positions and action log are
  not rebuilt. Forks at a round boundary work.

## References

- Scott-Phillips, T. C., Kirby, S., & Ritchie, G. R. S. (2009). Signalling signalhood
  and the emergence of communication. *Cognition*, 113(2), 226–233.
- Scott-Phillips, T. C., Kirby, S., & Ritchie, G. R. S. (2007). Signalling signalhood:
  An exploratory study into the emergence of communicative intentions. *Proceedings of
  the ESSLLI 2007 Workshop on Language, Games, and Evolution*, 78–84. The exploratory
  version of the same experiment, and the source of the game rules above.
- de Bie, P., Scott-Phillips, T. C., Kirby, S., & Verheij, B. (2010). Using software
  agents to investigate the interactive origins of communication systems. *Evolution
  of Language: Proceedings of the 8th International Conference (EVOLANG8)*.
- Scott-Phillips, T. C. The origins of human communication. *The Psychologist*, British
  Psychological Society.
