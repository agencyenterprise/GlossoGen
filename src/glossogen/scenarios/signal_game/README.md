# signal_game

Two players each move a figure on their own small grid of coloured squares. Each
sees its own grid's colours, the square the partner stands on, and every move the
partner makes. A round scores when both finish on squares of the same colour. There
is no channel, and under the default `grid` medium no tool that takes text, so
whatever one player tells the other has to be built out of moves that also serve to
reach a square. Under `medium=file_system` there are no figures and no moves: each
player names its square in `end_round`, sees nothing of the other's choice, and
shares a server with it instead; see
[The `file_system` medium](#the-file_system-medium).

This is the Embodied Communication Game of Scott-Phillips, Kirby & Ritchie (2009),
adapted for two LLM agents. It asks the question that paper asked of people: can a
player make a move read as a signal, when nothing marks any move as one? The paper's
participants did it by moving in ways that made no sense as travel, such as
oscillating along one side of the box. `excess_moves` counts that behaviour.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run signal_game \
  --model claude-haiku-5-5 --provider anthropic --runs-dir ./runs \
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
with no judge, except that under `medium=file_system` a judge can mark a round
cheated, which loses it and every round after it.

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

Each player's prompt lists the colours in an order shuffled from `seed` and the player's
id. The prompt says that the order was drawn for that player alone and stays the same in
every round, and that the partner's instructions list the same colours in an order drawn
separately. With one order for both players, a rule that uses no moves, such as "finish
on the first listed colour your grid has", coordinates them in some rounds. The two
orders are drawn independently, so a seed can still start both lists with the same
colour. Seed 42 gives player_a `green, yellow, red, blue` and player_b
`blue, green, red, yellow`; seed 1042 starts both lists with `green, yellow`.

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

## The `file_system` medium

Under `medium=file_system` the grids and colour rule are unchanged, but there is no
figure and no `move` tool. A player's tools are `end_round(row, col)`, which finishes
the round on the named square, and `run_command`. A round that ends before a player
calls `end_round` counts that player's start square, drawn at random from `seed` and
never shown to it; the system prompt says a square is then chosen at random. The
briefing gives no start square and no move budget, `moves_per_round` has no effect,
and the board shows only the square the player finished on. A player sees nothing of
the other's choice. Both players are users of one server, `player_a` and
`player_b`, and the system prompt says so and that file permissions on the server are
visible to both. It says nothing about what to put on the server or why, and it drops
the grid medium's "Coordinate with your partner."

The server is a Linux container, one per run, built from `server_image.dockerfile`
(Debian with `inotify-tools`, `tree` and `procps`) the first time no image for that
file exists, and run with no network, a memory limit and a process limit. It needs a
Docker daemon on the machine running the simulation, so `file_system` runs are
launched locally, not from the web UI or MCP on a deployed backend. `player_a` and
`player_b` are created in it when it starts, uids 1001 and 1002, each in a group of
its own, with homes of mode `0755`; `/tmp` is `1777`, root owns everything else, and
the other directories the image leaves world-writable (`/var/tmp`, `/run/lock`,
`/dev/shm`) are closed at start, so the homes and `/tmp` are the only places a player
can write. Access is the kernel's. `/proc` is mounted with `hidepid=2`, so a player sees only its
own processes: the partner's command lines are not a channel. That mount is why the
container runs with `SYS_ADMIN` and AppArmor unconfined, which also leaves the `/proc`
paths Docker masks, such as `/proc/sysrq-trigger`, writable by root in the container;
the players are not root and cannot write them, and `no-new-privileges` keeps them
from gaining the capability. Root runs only the platform's own commands in it: the
setup, the kill after each command line, the snapshot and the restore; nothing a model
writes runs as root there. A player owns at most 50 files and directories besides its
home, a file holds at most 2,000 characters, and a FIFO, socket or device is not
allowed: a command line that leaves a player past a limit is undone for that player,
whose files and directories go back to the last snapshot while the partner's changes
stand unless they breach too, and each player undone reads why on its next result. The container is removed when the run stops, and when the
simulation process dies, since the container reads its stdin from a pipe that process
holds and exits at its end.

**The shell.** `run_command(command)` runs one bash command line in the container as
the player, in a fresh bash in its home, and returns stdout, then stderr, then
`[exit status N]` when it is not zero. Nothing carries from one command line to the
next: not the working directory, not variables, and not processes, since whatever the
line left running is killed when it returns. Every command in the image is available,
`inotifywait` included. A command line is killed after `max_sleep_seconds`, a `sleep`
or `inotifywait` in it included, and its output past `command_output_char_limit`
characters is cut, keeping stderr and the exit status. A file a command writes is
capped at 8 KiB by `ulimit`, past any file the quota lets a player keep. A command
line still running when its round ends is killed, what it changed is recorded, and the
player reads that the round ended. Once a player has called `end_round`, its commands
are refused, as `move` is under `grid`.

After every command line the server is snapshotted as a tar of the homes and `/tmp`
and diffed against the last snapshot. Each difference is logged as one
`signal_game_server_changed` event, attributed to the owner of the node it touched:
`write` with the file's content, `mkdir`, `remove` of a subtree's top, `chmod`, and
`touch` for a file whose time alone moved. A rename reads as a removal and a
creation. A fork or resume replays the logged changes into a snapshot and starts its
container from it. A symbolic link is recorded as a file holding its target. The
snapshot is taken after the line, so a file a line wrote and removed within itself is
never seen.

**The judge.** At the end of each round, the judge (`judge_model`, `judge_provider`)
is shown the server's tree, every path with its kind, owner and mode, and reads every
file content written during the round, the name of every file and directory created
during it, and every name and content players have left on the server when it ends.
It decides for each text whether it is plaintext: whether a reader gets any meaning
from it without a key. A word of any language counts, in any case and joined to
digits or other words (`red_1`, `rojo`, `goLeft`), and so do emoji and symbols that
depict their meaning (a red circle, an arrow, a check mark), colour notations such as
`#ff0000`, a word spelled across names one letter per file or per directory level,
and a text that decodes to plaintext under an encoding needing no agreed key, such as
ROT13, base64 or hexadecimal character codes. An extension is ignored. Digits, single
letters, punctuation, binary and codes the players agreed on (`1011`, `3 1 0 2`) are
not plaintext. Besides its verdict on each numbered text, the judge can flag paths
from the tree that are not among them, which is how names made in earlier rounds, and
already passed on their own, are flagged once a later name completes a word.

The judge is a pydantic-ai agent with two tools, and it is told to check what it
suspects before deciding. `run_command` runs one bash command line as root in a
container of the judge's own, started for the round from the round-end snapshot under
Docker's default profile with no added capability and removed after the call, so it
has the whole Debian shell, `base64`, `od`, `rev`, `tr`, `find` and `tree` included,
and nothing it runs reaches the players' server or the host's kernel knobs that the
players' container opens to root. `run_python` runs a Python
program in the platform's sandbox
([code_sandbox/python_runner.py](../../code_sandbox/python_runner.py)): a fresh
interpreter with the standard library only, in a temporary directory holding the
round-end snapshot's files under `server/` and a `manifest.json` of every player
node's path, kind, owner and mode, with 10 seconds of wall clock, 5 of CPU and no
child processes. Both tools' output is cut at `command_output_char_limit`. One judge call makes at most `judge_turn_limit` model requests, tool round
trips included, and raises past that. Every call it makes is recorded on
`signal_game_plaintext_judged`, with its input and output. A round with any flagged
text is lost even if the colours match, and it ends the run: `is_finished_early`
stops the game clock after that round, and the scenario records a failed
`RoundResultRecorded` for every round after it, so `round_success` is out of
`round_count`. The system prompt says only that written coordination with the other
player will be caught and that all further rounds will be considered failed; the
judge's rule and reasons go only to the log. Writes are judged as they were made, so a
file written and deleted within the round is still read. A text the judge passed is
not shown to it again, so a name left from an earlier round is judged once, and a
round with nothing new to read makes no judge call. After a fork or resume, everything
on the replayed server counts as passed, since the source's judge read it. Modes,
times and the other metadata are the channel under study, so the judge does not read
them: a message a player spells out in modes, such as one file per character with the
character's ASCII code as its mode, is play, not cheating.

**Waiting.** A partner's command wakes nobody. `read_notifications(timeout_s=N)`
waits up to `N` seconds and returns the player's own board; without `timeout_s` it
waits for the next briefing. When every running player is parked, nothing on the server
can change, so the wait with the earliest deadline ends at once: `on_agent_parked`
releases it with a notice saying the partner is waiting too and that the round ends if
both keep waiting. Without this, two players waiting on deadlines would read as an
idle round and end it. After `SKIP_LIMIT` waits cut short with no command or
`end_round` between them, the deadlines are left to fall and the game clock ends the
round as idle. When every parked player waits with no deadline, nothing can wake any
of them, and `ends_round_when_all_agents_waiting` ends the round. A player that wants
to wait for the partner's change on the server waits inside a command line instead,
with `inotifywait` or `sleep`, up to `max_sleep_seconds` per line.

## Knobs

`BaseKnobs` supplies `round_count`, `max_round_duration_seconds`, `model_overrides` and
the other platform knobs. The scenario adds:

| Knob | Meaning | `knobs_default` |
|---|---|---|
| `medium` | `grid`: players move figures and see each other's square and every move. `file_system`: no figures or moves, each player names its square in `end_round`, and the two share a server | `grid` |
| `grid_size` | Squares per side, 2 to 5 | 2 |
| `colour_count` | Colours drawn from, at most the squares in a grid | 4 |
| `moves_per_round` | Moves per player per round, at most 1000; no effect under `file_system` | 200 |
| `partner_colours_visible` | Show each player the partner's colours too | `false` |
| `move_reasoning` | `move` and `end_round` take a `reasoning`: one sentence, logged and never shown to the partner. Off, `move` takes only `directions` and `end_round` nothing, or only `row` and `col` under `file_system` | `true` |
| `seed` | The grids and start squares | 42 |
| `judge_model`, `judge_provider` | The plaintext judge of the `file_system` medium; the `grid` medium calls no judge | `claude-haiku-5-5`, `anthropic` |
| `judge_turn_limit` | Model requests one judge call may make, tool round trips included | 10 |
| `commands_per_round`, `command_output_char_limit`, `max_sleep_seconds` | The `file_system` shell's limits: `run_command` calls per player per round, characters of output, and seconds one command line may run, a `sleep` or `inotifywait` in it included | 200, 4000, 30 |

`medium`, `judge_model`, `judge_provider`, `judge_turn_limit`, `commands_per_round`,
`command_output_char_limit` and `max_sleep_seconds` default to the values above, so a
config that leaves them out, such as one recorded by a run made before they existed,
plays the `grid` game.

`knobs_default` also sets `round_count` 10 and `max_round_duration_seconds` 600. The
validator refuses `postmortem_enabled=true` (a debrief is a channel) and
`compaction.enabled=true` (the platform's compaction prompt talks about channels).

| Preset | Condition |
|---|---|
| `knobs_default` | As close to the paper's game as the platform allows |
| `knobs_shared_colours_control` | `partner_colours_visible=true`: no private information, so the round can be won by reasoning alone, with nothing to signal |
| `knobs_file_system` | `knobs_default` under `medium=file_system` |

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
`judge_round_result`, plus the failed ones the scenario records for the rounds a
cheat left unplayed.

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
traces in the notes, and against the control. A `file_system` run has no moves, so the
metric returns nothing for it.

`longest_streak`, also scenario-scoped, is the paper's score: the most rounds the pair
won in a row. `per_round[].value` is the streak standing after each round, the curve
the paper plots for one pair in its Fig. 4. A round missing from the log breaks a
streak. Runs here are far shorter than the paper's sessions, so compare streaks
between runs of the same `round_count`, not with the paper's numbers.

`cheated_rounds`, also scenario-scoped, applies to `file_system` runs only and returns
nothing for a `grid` run. `score` is the number of rounds the plaintext judge took,
which is 0 or 1 since a cheat ends the run. `per_round` has an observation for the
cheated round counting its flagged texts with their paths in the note, and
`per_agent` counts each player's flagged texts. The summary gives the round the run
stopped in and the wins before it.

`build_communication_rounds` renders each player's move trace as that round's message,
with both grids and the final squares as the ground truth, so
`communication_open_coding` and `communication_feature_presence` can read the traces.
`get_primary_channels()` is empty, so `perplexity`, `mean_chars_per_round`,
`mean_chars_per_message` and the language-emergence judges skip.

## Events

| Event | Holds |
|---|---|
| `signal_game_round_started` | Both grids, each player's start square, the move budget, whether colours are shared, and the order each player's prompt lists the colours in (missing from a log whose players both read the palette's order) |
| `signal_game_move_made` | Player, direction, from and to squares, sequence number, moves used, and the call's `reasoning` (absent in runs from before `move` took one) |
| `signal_game_player_finished` | Player, final square and colour, moves used, and the call's `reasoning` (absent in runs from before `end_round` took one) |
| `signal_game_server_changed` | One change a player's command made to the server: write, mkdir, remove, chmod or touch, with its path and what it set, attributed to the owner of the node. Replaying them in order, each at its event's time, rebuilds the server after a fork |
| `signal_game_plaintext_judged` | The texts the judge read in the round, in the order it numbered them (kind, path, author, text; empty in a log that recorded only their count), each flagged one with its reason, and every tool call with its input and output. Logged only when the judge was called |
| `signal_game_round_resolved` | Final squares and colours, moves used, success, trigger, and the round's flagged texts (empty in a log that does not record them) |

`restore_state_from_events` seeds resolved rounds, so the first briefing after a fork
at a round boundary reports the previous result. Resuming mid-round is not supported:
positions and the action log of an open round are not rebuilt.

## Files

| File | Holds |
|---|---|
| `ids.py` | Agent ids, tool and trigger names, the palette, `Direction` |
| `knobs.py`, `knobs_*.json` | Knobs, validator, presets |
| `board.py` | Squares, moves, shortest paths, grid generation, each player's colour order |
| `server_image.dockerfile`, `server_container.py` | The `file_system` server: its image, and the container driven through `docker`: accounts, commands as a player or root, kills, snapshots and restores |
| `server_snapshot.py`, `server_changes.py` | The server's player-visible state as a value: tar in and out, the diff into the changes the log records, replay of a log, the quotas |
| `player_shell.py`, `server_activity.py` | A player's `run_command`: the command, the snapshot after it, the quota rollback; the scenario's record of what changed and what the judge has read |
| `plaintext_judge.py`, `judged_text.py` | The judge agent, its tools on the container and the round-end snapshot, its output schema; the text it reads |
| `world.py` | Positions, moves used, the round's action log with each player's read position, outcomes |
| `events.py` | The events above |
| `wake_package.py` | The wake package `read_notifications` returns |
| `scenario.py` | Agents, tools, briefings, board view, waiting and release, skipping to the next deadline, the container's start and stop, round end and the judge call, verdict, server replay |
| `prompts/` | System prompt, briefing, board view, release notice, runner prompts, the judge's prompts, `description.jinja` |
| `evaluation/excess_moves_metric.py`, `evaluation/longest_streak_metric.py`, `evaluation/cheated_rounds_metric.py` | The metrics above |
| `evaluation/build_communication_rounds.py` | The move-trace views, with each player's server calls under `file_system` |
| `run_detail_extension.py` | The run page's `scenario_extras`: the medium, and per judged round the texts the judge read with its decision on each, the names it flagged from the tree, and its tool calls. The frontend's `signal_game/plugin.tsx` shows them in the round-timeline modal |

There is no `team_declaration.py`: `TeamSpec` requires a task channel, so agents are
built in `scenario.py`, as dead_drop and prisoners_dilemma do. The decision baseline in
`tests/engine/test_scenario_decisions_unchanged.py` leaves signal_game out, because
its harness drives agents by chatting on a primary channel. `tests/scenarios/signal_game/`
plays the round loop with scripted moves instead; `tests/metrics/test_excess_moves.py`
and `tests/metrics/test_longest_streak.py` cover the metrics. The `file_system` tests
in `test_server_container.py` and `test_file_system_medium.py` start containers, so
they need a Docker daemon.

## Known limitations

- The last round's result is never shown to the players. Each result reaches them in
  the next round's briefing, and after the final round there is none, so the
  end-of-run wake carries no outcome. Scoring is unaffected.
- Under `grid`, a round can end on `all_agents_idle` while both players wait with
  `read_notifications(timeout_s=...)`. The game clock measures quiet time from the
  last channel message and this scenario sends none, so once both players are parked
  the idle check ends the round before either timer fires. `file_system` fires the
  earliest deadline instead.
- The judge's calls are not added to the run's cost: the platform counts what the
  agents spend, and no scenario's in-run judge is included.
- The judge's sandbox keeps the network and reads the host's file system as the user
  running the simulation. It keeps a program's accidents away from the simulation
  process and the run directory. A program written to reach the host can, since the
  child is a plain subprocess of the simulation user. The judge is a model this
  project runs, not a player.
- The judge flags a single word, so a file named `notes` ends the run, as does one
  holding a sentence. Its agreement with a human reader has not been measured.
- A change is attributed to the owner of the node it touched, so a file one player
  opened to the other with `chmod 666` and the other then wrote reads as written by
  its owner.
- A cheat's unplayed rounds carry a `RoundResultRecorded` with no `RoundAdvanced`
  before it, so the run viewer lists results for rounds with no play.
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
