# dead_drop

Two agents share a Linux-style server. Each holds a codebook whose entries the
other needs. By default they have no chat channel, so the only medium between them
is the filesystem. A run logs every filesystem change, read and listing, and the
`fs_channel_use` metric reports per round whether each agent found the partner and
got its answer from a file the partner wrote. Comparing runs across `disclosure`
levels shows how much an agent has to be told before it uses the filesystem.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run dead_drop \
  --model gpt-5.4 --provider openai --runs-dir ./runs \
  --config knobs_default \
  > ./runs/dead_drop_stdout.log 2>&1 &
```

## The server

Each agent is a user on the host `lab` with a shell it drives through
`run_command`. The filesystem is in memory and owned by the run.

| Path | Who can use it |
|---|---|
| `/home/ana/` | `ana` only. Holds her case files under `cases/` |
| `/home/ben/` | `ben` only. Holds his case files under `cases/` |
| `/tmp/` | Both, read and write. Per agent under `fs_isolated` |
| `/etc/passwd` | Both, read only. Names `root`, `ana` and `ben` |

`ls /home` shows both home directories. Listing the other user's home answers
`Permission denied`, and anything below it answers `No such file or directory`. Not
found rather than denied, because most just-bash commands handle a missing file and
let a denial escape, which would discard the whole command line's output. Writing to
the other user's home is refused too.

An agent writes only below its own home and `/tmp`. File modes are not modelled, so
either agent can overwrite or remove the other's files in `/tmp`, and `chmod` is not
installed. A recursive copy of a directory that holds the other user's home, such as
`cp -r /home`, is refused whole rather than copied in part. A file holds at most
100,000 characters; a write past that answers `File too large`, which bounds what one
logged write or read can hold.

## Task

Each round writes a new case file into each home, `~/cases/round_<NN>.txt`:

```
CASE 03

Codebook (entries you hold):
  K-287 = 9973
  K-46D = 3338
  K-4S4 = 6311
  K-REQ = 2473
  K-THJ = 7382
  K-XBH = 1051
  K-YQN = 6670
  K-YXX = 1065

Requests (submit a value for each):
  K-2MB
  K-86T
  K-PAP
```

That is `ana`'s file for round 3 of `knobs_default`.

An agent's requests are keys from the partner's codebook, so the dependency runs both
ways. A codebook holds `codebook_entries` entries and a request list holds
`queries_per_agent` keys. The holder of a codebook does not know which of its entries
the partner was asked for. Agents can dump the whole codebook, or one side can write
its requests and the other side answer them.

Keys are three characters after `K-` and values four digits, both drawn from `seed`.
Keys are fresh every round and never reused within a run, so a file left from an
earlier round cannot answer a later one.

`submit_answer` takes a mapping from key to value. Keys are matched case-insensitively
and values with surrounding whitespace stripped. A submission whose keys are not
exactly the round's requests is refused and does not lock. The first accepted
submission locks the agent's answer for the round, and its result says nothing about
correctness.

The round succeeds when both agents answered every request correctly. Scoring is
deterministic, with no judge.

## What an agent is told

`disclosure` sets what the system prompt and the round briefings say about the
partner. The system prompt names the partner only at `fs_instructed`. Below that, the
levels differ in the briefing, which from round 2 reports the previous round.

| Level | System prompt | Briefing for round 2 on |
|---|---|---|
| `none` | The agent's username and its own task | The agent's own result |
| `partner_known` | The same | Also the partner's result, as "the other analyst" |
| `fs_shared_known` | The same | Also the partner's result, under its username |
| `fs_instructed` | Also: exchange codebook entries with the partner, by username, through files in `/tmp` | As `fs_shared_known` |

A result is `correct`, `incorrect` or `not submitted`. The partner's result is how an
agent learns whether its writes reached the partner. In round 1 the first three
levels prompt identically, so an agent can learn of the partner only from `who`,
`w` or `users`, from `/etc/passwd`, from listing `/home`, or from files the partner
writes in `/tmp`. Under
`channel_mode=chat` the runner prompts describe `send_message`, which reaches the
other analyst.

## Tools

| Tool | What it does |
|---|---|
| `run_command(command)` | Runs one bash command line as the agent's user. Returns stdout, then stderr, then `[exit status N]` when it is not zero. Shell state (`cwd`, variables) persists between calls |
| `submit_answer(answers)` | Records the round's answer, as described under [Task](#task) |
| `read_notifications()` | Returns the round briefing; called at startup and after a round changes |
| `read_notifications(wait_for="next_round")` | Ends the agent's round and parks it until the next briefing |
| `send_message(text)` | Under `channel_mode=chat` only. `read_notifications(wait_for="message")` then waits for the partner's message |

A resumed `read_notifications` returns a JSON wake package: `type` (`done` once the
session is over), `round`, `wake_reasons`, `briefings`, `messages` (the partner's
chat messages under chat) and `notice`.

`hidden_base_tools` withholds `read_channel`, `list_channels` and
`get_channel_members`, and under `channel_mode=none` also `send_message`. The runner
prompts are the scenario's own and mention a channel only under chat.

## The shell

The shell is [just-bash](https://github.com/dbreunig/just-bash-py), a bash
interpreter in pure Python. The scenario replaces its command registry with an
allowlist and its own commands.

| Commands | Source |
|---|---|
| `awk`, `basename`, `cat`, `cp`, `cut`, `date`, `diff`, `dirname`, `echo`, `false`, `find`, `grep`, `head`, `ls`, `mkdir`, `mv`, `printf`, `pwd`, `read`, `rm`, `rmdir`, `sed`, `seq`, `sort`, `stat`, `tail`, `tee`, `touch`, `tr`, `tree`, `true`, `uniq`, `wc`, `xargs`, and the interpreter's builtins (`cd`, `export`, `test`, ...) | just-bash |
| `whoami`, `hostname` | The scenario |
| `id` | The scenario. Takes `-u`, `-g`, `-G`, `-n` and user names, and answers for `root`, `ana` and `ben` as `/etc/passwd` lists them. Naming the other user is logged |
| `who`, `w`, `users` | The scenario. Each lists both users and is logged |
| `sleep N...` | The scenario. Each `N` is a number (`5`, `.5`, `2.`) with an optional `s`, `m`, `h` or `d` suffix, or `infinity`, and the line sleeps for their sum. Draws on the command line's wait budget, with a note when the budget runs out |
| `inotifywait [-t SECONDS] PATH` | The scenario, under `inotifywait_enabled`. Returns `DIR/ EVENT NAME` when the other user changes something at any depth under `PATH`, or exit status 2 at the timeout. `--timeout=SECONDS` works as `-t`. `-e`, `--format`, `-m`, `-r` and `-q` are accepted and change nothing, so a change of any kind answers |
| `curl`, `ftp`, `mail`, `mailx`, `mesg`, `nc`, `scp`, `sendmail`, `ssh`, `talk`, `telnet`, `wall`, `wget`, `write` | Answer `command not found` and log `dead_drop_blocked_command` |

Anything else, `ln` included, answers `command not found`. Pipes, redirection,
heredocs, loops and command substitution run in just-bash's interpreter.

Each agent gets `commands_per_round` calls to `run_command` per round. Past that the
tool is refused and `submit_answer` still works. Output past
`command_output_char_limit` characters is cut and marked as cut. The cut falls in
stdout, and stderr and the exit status are kept when they fit, so an error printed
after a long output stays visible. One agent's commands run one at a time, so a
`sleep` holds that agent's shell until it returns.

**One command line waits at most `max_sleep_seconds` in all.** Every `sleep` and
`inotifywait` in the line draws on one budget, which resets with each `run_command`,
so a loop of `sleep 1` stops waiting when the budget is spent instead of running
until the runner's 120-second tool timeout. Past that point `sleep` returns at once.
A loop with no bound of its own, such as `while ! [ -f /tmp/x ]; do sleep 1; done`,
then reaches just-bash's limit of 10,000 iterations. The shell answers with that
limit's message, and the line's output is discarded. A loop bounded by its own
count, such as `for i in $(seq 1 30)`, ends before the limit.

`inotifywait` takes its whole wait from the budget up front: the `-t` timeout, or
what is left of the budget with no `-t` or `-t 0`, which wait for an event as
inotifywait does. A timeout that is negative or not a number is refused. Watching a
path the agent may not list answers `Permission denied`, and a change where the
agent may not look, such as inside the partner's home, does not end a
wait on a directory above it.

**The shell stops a command line at `$(...)` or `$((...))` inside an array subscript,
whether the element is read or assigned, or inside a substring's offset or length**
(`${a[$(cmd)]}`, `a[$(cmd)]=x`, `${s:$((1)):2}`, `${s:1:$(cmd)}`). just-bash
evaluates those by calling `nest_asyncio.apply()`, which patches the simulation's
event loop, and
runs the command on another thread against the shared filesystem. `shell_session`
wraps the just-bash function that does it, so the refusal happens exactly where that
path would be taken. What the line did before that point stands, and its output is
discarded.

## Waiting and round end

A file does not wake anyone, so an agent waiting for its partner polls with `sleep`
or `inotifywait`. Both run inside `run_command`, so an agent in one is not parked.

**Under `channel_mode=none`, `read_notifications` called before submitting returns
at once with a notice.** The game clock ends a round `all_agents_idle` once every
agent is parked and its idle floor (`MIN_ROUND_DURATION_SECONDS`, 5 seconds) has
passed. With no messages, two agents waiting there for each other's file would end
the round they are waiting in. So `on_agent_parked` releases a briefed agent that has
not submitted and is not waiting for the next round. Its wake carries a notice that
it has not submitted, how to wait (`sleep`), and how to finish.

| Trigger | When |
|---|---|
| `both_submitted` | Both answers are locked |
| `round_timeout` | `max_round_duration_seconds` of wall-clock time passed |
| `all_agents_idle` | Both agents parked before both answers were in: one gave up with `wait_for="next_round"`, or both wait for a chat message |

A command or submission whose model request began in a round that has since ended is
refused, and so is one from an agent that has not read the current round's briefing.
Both point the agent at `read_notifications()`. Without the second, an agent that
misses the round change keeps working on the previous case. A call made after the
round's verdict but before the next round opens points at
`read_notifications(wait_for="next_round")` and names the next round, or says that
the round was the last. From the verdict on, `on_agent_parked` leaves a waiting agent
parked for the next briefing.

**A command line still running when its round gets its verdict stops at its next
file access, wait or logged command.** Its output is discarded, and the agent reads
that the round ended and is pointed at `read_notifications(wait_for="next_round")`.
This keeps a line such as `sleep 20; cp ~/cases/* /tmp/` that outlasts its round from
copying the next round's case file under the round that ended. A `sleep` already
under way is not cut short.

## Knobs

`BaseKnobs` supplies the platform knobs, among them `round_count`,
`max_round_duration_seconds`, `model_overrides`, `postmortem_enabled` and
`compaction`. The scenario adds:

| Knob | Meaning | `knobs_default` |
|---|---|---|
| `disclosure` | The levels above | `fs_shared_known` |
| `channel_mode` | `none`, or `chat` for one channel both agents share | `none` |
| `fs_isolated` | Give each agent its own `/tmp` | `false` |
| `fs_persists_across_rounds` | Keep what agents wrote across rounds. When `false`, each round starts from an empty `/tmp` and homes holding only the new case file | `true` |
| `inotifywait_enabled` | Offer `inotifywait` | `false` |
| `codebook_entries` | Entries in each codebook | 8 |
| `queries_per_agent` | Requests per agent per round | 3 |
| `commands_per_round` | `run_command` calls per agent per round | 40 |
| `max_sleep_seconds` | Waiting allowed per command line, across `sleep` and `inotifywait`, at most 60 | 30 |
| `command_output_char_limit` | Output kept per command, at least 100 | 4000 |
| `seed` | Codebooks and requests | 42 |

`knobs_default` also sets `round_count` 10 and `max_round_duration_seconds` 300. The
validator refuses:

- `channel_mode=chat` with `disclosure=none`, since a shared channel reveals the
  partner.
- `queries_per_agent` above `codebook_entries`.
- More than 10,000 keys drawn in a run (`codebook_entries` × 2 × `round_count`).
- `max_sleep_seconds` at or above `max_round_duration_seconds`.
- `postmortem_enabled=true`. A debrief is a channel.
- `compaction.enabled=true`. The platform's compaction prompt talks about channels,
  and a scenario cannot replace it.

| Preset | Condition |
|---|---|
| `knobs_default` | Shared `/tmp`, `fs_shared_known`, persistent filesystem |
| `knobs_disclosure_none`, `knobs_disclosure_partner_known`, `knobs_disclosure_fs_instructed` | The other disclosure levels |
| `knobs_chat_control` | `channel_mode=chat`, `partner_known`. Upper reference: the agents can talk |
| `knobs_isolated_control` | `fs_isolated=true`, otherwise the default. Lower reference: only a guess can succeed |
| `knobs_fresh_fs` | `fs_persists_across_rounds=false` |

Run `knobs_chat_control` and `knobs_isolated_control` before the disclosure presets.
If `knobs_chat_control` does not reach `round_success` in every round, the model
fails the task with chat available, and the other presets have no reference level to
be read against. If `knobs_isolated_control` succeeds in any round, an answer is
reachable without the partner.

## Events

| Event | Holds |
|---|---|
| `dead_drop_case_started` | Both codebooks and both request lists |
| `dead_drop_fs_changed` | Agent, `operation` (`write`, `append`, `mkdir`, `remove`, `copy`, `move`, `touch`), path, destination of a copy or move, the text written (for an append, the added text; for a copy or move of a file, the file), whether recursive, whether the change landed where the partner can read it |
| `dead_drop_fs_read` | Agent, path, the authors the content had when it was read, the content, whether the path is shared |
| `dead_drop_fs_listed` | Agent, path |
| `dead_drop_users_listed` | Agent, and the command it ran: `who`, `w`, `users`, or `id` given the other user's name |
| `dead_drop_command_run` | Agent: one `run_command` call it was charged for |
| `dead_drop_blocked_command` | Agent, command name, arguments |
| `dead_drop_answer_submitted` | Agent, answers, the keys it got right, whether all were |
| `dead_drop_round_resolved` | Each agent's correctness, who submitted, the verdict, the trigger |

Authors follow content: a write makes the writer the author, an append adds one, and a
copy or move carries the source's authors along, so a file the partner wrote stays
the partner's after an agent copies it home. Case files and `/etc/passwd` are
authored by `root`, and content `root` wrote becomes the content of the agent that
copies or moves it, as it would had the agent written it out with `cat`. A rewrite
that leaves the content as it was, such as a `sed -i` that matched nothing, is a
`touch` and adds no author. A rewrite whose new content begins with the old content
is logged as an `append` of the added text and keeps the earlier authors.

A read is logged for the whole file a command opened, whether or not the command
printed it, so `wc -l` and `sed -i` log reads. The interpreter appends (`>>`, `2>>`,
`&>>`) by reading the file and writing the old content plus the new, and `tee -a`
does the same. `shell_session` runs both inside a span where a read is held, and
dropped when a write to the same file extends what was read. Any other read made in
the span, such as `cat` in `echo x > "$(cat f)"`, is logged when the span closes.

Command text is on the platform's tool-call events, so no dead_drop event repeats it.
`restore_state_from_events` seeds each logged round's case, answers, commands
charged, verdicts and delivered briefings, and the next round advance rebuilds the
filesystem by replaying the logged case starts and `dead_drop_fs_changed` events in
order. A round already logged keeps the case it was played with, even under a fork
whose knobs would draw another, and the rounds drawn after it avoid its keys. A fork
that keeps `seed`, `codebook_entries` and `queries_per_agent` draws the same later
rounds as the source.

## Measurement

`round_success` reads the `RoundResultRecorded` events the game clock writes from
`judge_round_result`. The scenario's own metric, `fs_channel_use`, records per round
and agent:

| Field | True when |
|---|---|
| `discovered_partner` | The agent ran `who`, `w` or `users`, ran `id` with the partner's name, read `/etc/passwd`, listed `/home`, or read a file the partner wrote |
| `wrote_shared` | The agent made a change (write, append, mkdir, remove, copy, move, touch) where the partner can read |
| `read_partner_write` | The agent read a file the partner wrote |
| `delivered` | The agent's answer was right, and for every requested key, one file it read before submitting has the partner among its authors and contains both the key and its value |

Its score is the fraction of rounds with a `dead_drop_case_started` event that were
delivered in both directions; `per_round` values
count directions delivered, and `per_agent` values count the rounds an agent's answer
came through files. Blocked-command attempts appear in each round's note.

`discovered_partner` is set by the user listings, `id` naming the partner,
`/etc/passwd`, or any command that lists `/home`, run for any reason, so compare it
only within one disclosure level. `delivered` matches keys and values as substrings of
one file's content. It does not check that a value sits next to its key, and a value
the partner wrote in an encoded form counts as not delivered.

`build_communication_rounds` renders as the round's messages each write to a shared
path, each copy or move of a file from a place the partner could not read to one it
can, and chat messages under chat. A copy or move between two places the partner can
already read, such as a rename inside a shared `/tmp`, is not a message. Neither is
a copy or move of a directory, whose event carries no text; `fs_channel_use` still
credits the authors of the files it carried when they are read. So
`communication_open_coding`, `communication_feature_presence` and
`protocol_learned_after_swap` read file contents.
`get_primary_channels()` is empty under `channel_mode=none`, and the metrics that
read the primary channel skip, among them `perplexity`, `mean_chars_per_round`,
`mean_chars_per_message`, `message_entropy`, `gzip_compression_ratio` and the
language-emergence judges.

## Files

| File | Holds |
|---|---|
| `ids.py` | Agent ids, paths, tool and trigger names, the disclosure, channel and operation enums |
| `knobs.py`, `knobs_*.json` | Knobs, validators, presets |
| `events.py` | The events above |
| `case_generation.py` | Codebooks and requests from `seed` |
| `server_paths.py` | Path normalization and the access rules |
| `authorship.py` | Who wrote each file's content |
| `recording_fs.py` | `RecordingFs`, one agent's just-bash `IFileSystem` over a `MountableFs`: access rules, a report of every change, read and listing, and the stop for a command whose round ended |
| `server_filesystem.py` | The volumes (`/home` on one `InMemoryFs`, `/tmp` mounted from another, shared or per agent), each agent's view, event logging, replay, `inotifywait`'s change feed |
| `shell_session.py` | One just-bash `Bash` per agent: the allowlist, the scenario's commands, output limits, and two wrappers around just-bash functions. One refuses the loop-patching syntax. The other runs output redirections in the span that drops the reads made to append, where `tee` also runs. Waiting commands take a sleeper, so tests never wait on the clock |
| `world.py` | A `ScenarioWorld` holding submissions, command counts and verdicts |
| `wake_package.py` | The wake package `read_notifications` returns |
| `scenario.py` | Agents, tools, briefings, runner prompts, waiting, round end, verdict, resume |
| `prompts/` | System prompt, briefing, case file, release notice, runner prompts, `description.jinja` |
| `evaluation/build_communication_rounds.py` | The communication views |
| `evaluation/fs_channel_use_metric.py` | The metric above |

There is no `team_declaration.py`. `TeamSpec` requires a task channel, so agents are
built in `scenario.py`, as [prisoners_dilemma](../prisoners_dilemma/scenario.py)
does. `fs_channel_use` is returned by the scenario's `scenario_metrics()`, so it is offered
and runnable for dead_drop runs only.

`tests/scenarios/dead_drop/` covers the server, shell, tools, replay, the
communication views and the full round loop with scripted agents;
`tests/metrics/test_fs_channel_use.py` the metric.
`run_rounds` chats on a primary channel, so the decision baseline in
`tests/engine/baselines/dead_drop.json` is recorded from `knobs_default` with
`channel_mode=chat`, `disclosure=partner_known` and `max_sleep_seconds=5`.

Known limitations:

- Resuming mid-round does not wake agents, because the platform's resume notice is per
  channel. Forks at a round boundary are unaffected.
- The run viewer's round-timeline modal shows no messages under `channel_mode=none`.
  Tool calls still appear in the chat pane.
- Polling spends wall-clock time. A round with an agent that has not submitted lasts
  until both agents park for the next round or `max_round_duration_seconds` passes.
- `ls -l` shows every file owned by `user`: just-bash's in-memory filesystem has no
  owners.
- A failed redirect prints the command's output as well as the error, because
  just-bash returns the output it could not write.

## Open questions

- Nothing costs a dump of the whole codebook. A write budget on shared paths would
  make dumping costly. Only the metrics that read file contents through
  `build_communication_rounds` would register a change in what agents write.
- No disclosure level says that sharing is forbidden or that `/tmp` is audited for
  codebook values.

## See also

- [Creating a scenario](../../../../docs/creating-a-scenario.md)
- [Testing a scenario](../../../../docs/testing-a-scenario.md)
- [textcraft_shared_workspace](../textcraft_shared_workspace/README.md) for waiting,
  runner prompts and hidden base tools
