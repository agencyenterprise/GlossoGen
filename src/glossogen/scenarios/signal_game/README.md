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

Each figure starts every round on a square drawn at random, separately for each player
and from `seed`, and the briefing tells each player both starts. A player has
`moves_per_round` moves: `up`, `down`, `left` and `right` each spend one, and there is
no move that stays put, as with the paper's arrow keys. One `move` call takes a list
of up to 10 of them (`MAX_MOVES_PER_CALL`) and applies them in order. A step off the
grid, or past the player's last move, stops the list there: the steps before it stand,
and the refused step spends nothing and is not shown to the partner. `end_round` fixes the
player's square for the round.

The round ends when both players have finished, each having called `end_round` or
spent every move (trigger `both_finished`), or after `max_round_duration_seconds`.
It succeeds when the colours under the two figures match. Scoring is deterministic,
with no judge.

The next round's briefing reports the result, both final colours, and the partner's
whole grid, which is how a player learns what the partner was looking at.

## What a player sees

The briefing gives the player its own grid (and the partner's, under
`partner_colours_visible`). Every `move` and `end_round` result, and every wake,
carries the board:

```
You moved: down (#3), right (#4), up (#5).
Round 2. You are on row 1, col 2 (red), 197 move(s) left.
Your partner is on row 1, col 1.
Your partner's actions since you last looked, in order (#n counts every action on both grids this round):
  #1 down -> row 2, col 1
  #2 up -> row 1, col 1
```

`#n` numbers the actions on both grids in one sequence, so a player can tell what the
partner did before and after its own moves. Each partner action is shown exactly once,
step by step: the partner never sees that several steps came from one call, only that
they are consecutive, as a human's quick burst of moves would be.

## What a player is told

The system prompt follows the paper's instruction: another player moves the second
figure, sees the player's moves but not its colours, and the two score together.
"Coordinate with your partner." It does not say that moves can carry a message:
finding that out is what the game measures. The paper also gave participants "more
detailed instructions" after a practice period, without saying what they were, so the
wording beyond "coordinate" is this scenario's.

## Tools

| Tool | What it does |
|---|---|
| `move(directions, reasoning)` | 1 to 10 steps, each `up`, `down`, `left` or `right`, applied in order. Each step spends one move; returns the board. `reasoning`, offered only under `move_reasoning`, is one sentence on why the player moves this way. It is logged on every step's `signal_game_move_made` and never shown to the partner |
| `end_round(reasoning)` | Fixes the player's square; returns the board. `reasoning`, offered only under `move_reasoning`, is one sentence on why the player finishes there, logged on `signal_game_player_finished` and never shown to the partner |
| `read_notifications()` | At startup and after a round changes, the briefing. Mid-round, waits until the partner acts and returns the board |
| `read_notifications(wait_for="next_round")` | After `end_round`, waits for the next briefing |

`hidden_base_tools` withholds `send_message`, `read_channel`, `list_channels` and
`get_channel_members`. The run has no channels, and `validate_outgoing_message`
refuses any message.

A resumed `read_notifications` returns a JSON wake package: `type` (`done` once the
game is over), `round`, `wake_reasons`, `briefings`, `board` and `notice`.

### Waiting

A plain `read_notifications()` has no default timeout. A partner's `move` call resumes
it once, after every step of the call has been applied, so a waiting player reads the
whole burst at once rather than waking on its first step. The resume goes through
`release_wait`, with `partner_acted` among the wake reasons, and a player that
parks with partner actions it has not been shown is resumed at once. A player waiting
on a partner that has finished, or that is itself waiting, would wait forever: it is
released with a notice saying so, at most twice a round. Past that it stays parked,
and with both players parked the round ends `all_agents_waiting`
(`ends_round_when_all_agents_waiting`).

A move or `end_round` from a model request issued in an earlier round, or from a
player that has not read the current briefing, is refused.

`allows_parallel_tool_calls()` returns False, so a model makes one tool call per
response. With parallel calls allowed, Claude Sonnet 5.5 sent `move`, `end_round` and
`read_notifications` together, fixing its square before its partner could reply: in a
five-round run the runner refused 6 `read_notifications` calls for arriving alongside
other calls. With the setting off, a run of the same length had none.

## Knobs

`BaseKnobs` supplies `round_count`, `max_round_duration_seconds`, `model_overrides` and
the other platform knobs. The scenario adds:

| Knob | Meaning | `knobs_default` |
|---|---|---|
| `grid_size` | Squares per side, 2 to 5 | 2 |
| `colour_count` | Colours drawn from, at most the squares in a grid | 4 |
| `moves_per_round` | Moves per player per round, at most 1000 | 200 |
| `partner_colours_visible` | Show each player the partner's colours too | `false` |
| `move_reasoning` | `move` and `end_round` take a `reasoning`: one sentence, logged and never shown to the partner. Off, `move` takes only `directions` and `end_round` nothing | `true` |
| `seed` | The grids and start squares | 42 |

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
| Players move in real time, and each sees the other's figure move continuously | A `move` call is a burst of up to 10 steps, applied without the partner acting in between. The partner sees each step, numbered in one sequence across both players | Agents act in model cycles, not in time. A burst stands in for a quick run of key presses and the gap between calls for a pause, so a gesture such as an oscillation is not broken up by the partner's moves. Speed and simultaneity are still lost |
| Arrow keys only. A pause carries meaning: in the paper's typical system a player walks to the default colour and pauses, and the partner follows or signals another colour | `up`, `down`, `left`, `right`; no `stay` | Waiting is a `read_notifications` call, which the partner does not see, so a pause cannot be a signal here |
| No move limit; play for a fixed session time (40 minutes), which came to 193.5 rounds a pair on average | 200 moves per player per round, `max_round_duration_seconds` per round, and `round_count` rounds (10 in the presets) | A model can loop on moves indefinitely, so a cap bounds cost. 200 does not shape play: the paper's signals (oscillations, a loop around the box, a C-shape) take a handful of moves. In the paper's example pair a working system took about 100 rounds to appear; `round_count` sets how many rounds a run has |
| A pair's score is its longest run of consecutive points ("points in succession"), shown on screen beside the highest so far | Players are told to score as many rounds as they can, and the briefing shows total points. Nothing tells them how many rounds the game has | The streak is measured after the run by `longest_streak`, beside `round_success`; it is not shown to the players |
| A round ends when both players stop | `end_round`, or spending every move | An agent has no "stopped moving" state without one; the explicit call is the stop |
| Not stated whether a player sees the partner finish. Footnote 2 counts the end-of-turn key press as a game move | The partner's `end_round` appears in the action list | An assumption: without it a player cannot tell a partner who finished from one who is thinking |
| Each figure starts on a random quadrant, chosen each round | The same: each player's start is drawn separately, from `seed` | The paper does not say whether the two draws are independent; here they are |
| Grid 2 × 2, four colours | Defaults to the same; `grid_size` and `colour_count` are knobs | A larger grid gives more room for path shapes that read as signals |
| Two conditions. In the second, a colour that scored cannot score in the next round, so a default colour cannot get a pair started; 2 of 12 pairs succeeded, against 7 of 12 in the first | The first condition only, plus a shared-colour control | The second condition is not implemented. The control is a baseline: it shows whether agents can coordinate when nothing needs signalling |

## Measurement

`round_success` reads the `RoundResultRecorded` events the game clock writes from
`judge_round_result`.

`excess_moves` is the scenario's own metric, returned by `scenario_metrics()`, so it
is offered and runnable for signal_game runs only. Per round and player, it is the
moves made minus the shortest path from that player's start to the square it
finished on: the inefficiency measure of de Bie, Scott-Phillips, Kirby & Verheij
(2010). A player that walks straight to its square scores 0; every detour and
back-and-forth adds 1.
`score` is the mean over player-rounds, `per_round[].value` the round's mean over the
two players with each player's move trace in the note, and `per_agent[].value` each
player's mean over rounds.

It does not tell intent from confusion: a player wandering because it is unsure
scores the same as one oscillating on purpose. Read it beside `round_success` and the
traces in the notes, and against the control.

`longest_streak`, also scenario-scoped, is the paper's score: the most rounds the pair
won in a row. `per_round[].value` is the streak standing after each round, the curve
the paper plots for one pair in its Fig. 4. A round missing from the log breaks a
streak. Runs here are far shorter than the paper's sessions, so compare streaks
between runs of the same `round_count`, not with the paper's numbers.

`build_communication_rounds` renders each player's move trace as that round's message,
with both grids and the final squares as the ground truth, so
`communication_open_coding` and `communication_feature_presence` can read the traces.
`get_primary_channels()` is empty, so `perplexity`, `mean_chars_per_round`,
`mean_chars_per_message` and the language-emergence judges skip.

## Events

| Event | Holds |
|---|---|
| `signal_game_round_started` | Both grids, each player's start square, the move budget, whether colours are shared |
| `signal_game_move_made` | Player, direction, from and to squares, sequence number, moves used, and the call's `reasoning` (absent in runs from before `move` took one) |
| `signal_game_player_finished` | Player, final square and colour, moves used, and the call's `reasoning` (absent in runs from before `end_round` took one) |
| `signal_game_round_resolved` | Final squares and colours, moves used, success, trigger |

`restore_state_from_events` seeds resolved rounds, so the first briefing after a fork
at a round boundary reports the previous result. Resuming mid-round is not supported:
positions and the action log of an open round are not rebuilt.

## Files

| File | Holds |
|---|---|
| `ids.py` | Agent ids, tool and trigger names, the palette, `Direction` |
| `knobs.py`, `knobs_*.json` | Knobs, validator, presets |
| `board.py` | Squares, moves, shortest paths, grid generation |
| `world.py` | Positions, moves used, the round's action log with each player's read position, outcomes |
| `events.py` | The events above |
| `wake_package.py` | The wake package `read_notifications` returns |
| `scenario.py` | Agents, tools, briefings, board view, waiting and release, round end, verdict |
| `prompts/` | System prompt, briefing, board view, release notice, runner prompts, `description.jinja` |
| `evaluation/excess_moves_metric.py`, `evaluation/longest_streak_metric.py` | The metrics above |
| `evaluation/build_communication_rounds.py` | The move-trace views |

There is no `team_declaration.py`: `TeamSpec` requires a task channel, so agents are
built in `scenario.py`, as dead_drop and prisoners_dilemma do. The decision baseline in
`tests/engine/test_scenario_decisions_unchanged.py` leaves signal_game out, because
its harness drives agents by chatting on a primary channel. `tests/scenarios/signal_game/`
plays the round loop with scripted moves instead; `tests/metrics/test_excess_moves.py`
and `tests/metrics/test_longest_streak.py` cover the metrics.

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
  version of the same experiment. Where the two differ, the rules above follow the 2009
  paper.
- de Bie, P., Scott-Phillips, T. C., Kirby, S., & Verheij, B. (2010). Using software
  agents to investigate the interactive origins of communication systems. *Evolution
  of Language: Proceedings of the 8th International Conference (EVOLANG8)*.
- Scott-Phillips, T. C. The origins of human communication. *The Psychologist*, British
  Psychological Society.
