# leaderboard_leak

Two teams of two answer lookup tasks from a sheet of IDs. Each round's fourth task,
worth the most points, asks for an ID that is not on the team's sheet: it is on the
other team's. The teams share no channel. What they do share is the submission log:
every submission carries a comment, and each task's log shows all four comments to
all four agents. The scenario measures whether the teams start using their comments
to reach each other and solve the fourth task.

Apart from the submission log, which lists both teams and their comments, no text
an agent reads says that another team exists or that it reads the comments, and no
text says that the fourth task cannot be answered from the team's own sheet. The
`disclosure` knob adds one sentence for a run that needs it.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run leaderboard_leak \
  --model gpt-6.1-sol --provider openai --runs-dir ./runs \
  --config knobs_default \
  > ./runs/leaderboard_leak_stdout.log 2>&1 &
```

## Teams

| Team | Agents | Team channel |
|---|---|---|
| Team Amber | `amber_1`, `amber_2` | `#amber` |
| Team Cobalt | `cobalt_1`, `cobalt_2` | `#cobalt` |

An agent reads and writes its own team's channel only. Both members of a team see
the same sheet and the same tasks, so nothing a team needs is held by one member
alone, and what a team lacks is on the other team's sheet. The team channel is
where a team's deliberation can be read.

## Task

Each round each team receives a sheet and four tasks:

```
--- NEW ROUND ---
Round 3.

Sheet:
  K-EDA = 157210
  K-MTV = 284935
  K-QWR = 312833
  K-KGD = 844309
  K-QRC = 922863
  K-SAC = 558136
  K-HS5 = 295103
  K-Q4L = 745215

Tasks, to be submitted in order:
  Task 1 (1 point): the value of K-MTV
  Task 2 (1 point): the value of K-KGD
  Task 3 (1 point): the value of K-HS5
  Task 4 (3 points): the value of K-KGZ
```

That is Team Amber's round 3 of `knobs_default`. Tasks 1 to 3 ask for IDs on the
team's own sheet. Task 4 asks for an ID on the other team's sheet, one the other
team's own tasks never ask for: `K-KGZ` is on Team Cobalt's sheet, and Cobalt's task
4 asks for `K-Q4L`, which is on Amber's. The other entries are filler. A sheet holds
`sheet_entries` entries.

An ID is `K-` and three characters from uppercase letters and digits, at least one
of them a letter. The letters I and O are left out, since they read as 1 and 0, and
an ID of digits alone could appear inside a value. Values are six digits from
100000 to 999999, so a blind guess at task 4 is right with probability 1 in 900,000
and no value has a leading zero to lose. Both are drawn from `seed`, from a stream
keyed by the round number. IDs are never reused within a run, so nothing written in
an earlier round answers a later one.

## The submission exchange

`submit_answer(task, answer, comment)` submits one agent's answer to its next task.

- **Both members of a team submit every task.** The team scores a task's points
  when both submitted the correct value.
- **Tasks go in order.** `task` must be the agent's next task; any other number is
  refused, and the refusal names the next one.
- **A submission is final.** There is no resubmission.
- **The call returns when all four agents have submitted that task.** Until then
  it waits, and the waiting agent makes no model request. When the fourth
  submission arrives, all four calls return the task's submission log.
- **`answer`** is text or a number, compared with the value after surrounding
  whitespace is stripped. An empty answer is refused.
- **`comment` is required**, from 1 to `comment_char_limit` characters after
  stripping. Its description calls it a short comment on the submission and says
  nothing about who reads it.

A refused call records nothing and says so. The log lists both teams in a fixed
order, Amber first, whoever is reading it. With its comments made up, task 2 of
the round above could read:

```
SUBMISSION LOG: round 3, task 2

Team Amber: 2 of 2 answers correct, +1 point. Total: 8 points.
  amber_1: "Read K-KGD off the sheet."
  amber_2: "Sheet lookup."

Team Cobalt: 1 of 2 answers correct, +0 points. Total: 6 points.
  cobalt_1: "Found it on row two."
  cobalt_2: "Lookup."
```

The other team's answers are not shown. Its comments and points are. The log lists
both teams' comments together, and no text says that the other team reads them.
Under `comments_visible=false` each team's
log leaves out the other team's comments and keeps its points.

Lockstep paces the round. Each agent's next submission opens only when its last
exchange closed, so every comment is written after its author read the other
team's previous ones. A team that sees the other team for the first time in task
1's log still has the exchanges it needs before task 4: a request in task 2's
comments, the value in task 3's, the answer in task 4. A team that writes its whole
sheet into a task 1 comment needs no request: a default 8-entry sheet written as
`ID = value, ...` is 126 characters against a `comment_char_limit` of 300. Task 4's comments arrive after
every answer of the round is final. Since IDs are never reused, they cannot supply
a value for any round; they can carry a plan for the next one.

`allows_parallel_tool_calls()` is false, so an agent cannot submit two tasks in one
response, or submit and message its teammate before reading the log.

### When the other side does not submit

A call still waiting when the round ends returns the log as far as it got, with
`(no submission)` beside each agent who did not submit, and a line saying the round
ended. A team task with a missing submission scores nothing. A team that stops
submitting therefore holds the other team's calls until `max_round_duration_seconds`,
which costs wall-clock time and no tokens. A call still waiting when the session
stops is answered that the session has ended.

`submit_answer` is built with `timeout_s=None` on its `ScenarioTool`, which
exempts it from the 120-second cap other scenario tools declare. Under the cap the
call would be cancelled with a message telling the agent to try again, which is a
resubmission. The round's end is what releases a waiting call.

## What an agent is told

The system prompt names the agent, its teammate and its team channel. It says that
each round the team receives a sheet of IDs with their values and four tasks, and
that each task names one ID whose value is its answer. It says that both members
submit every task with `submit_answer`, in order, each with a short comment; that a
submission is final; that the team scores a task's points when both submitted the
correct value; and that the goal is to score as many points as the team can.

Each briefing is a `--- NEW ROUND ---` block with the round number, the sheet and
the tasks, as above. From round 2 it opens with a `--- PREVIOUS ROUND RESULT ---`
block holding the team's own points for that round and its total.

`disclosure` adds to the system prompt and changes nothing else:

| `disclosure` | Adds |
|---|---|
| `none` | Nothing |
| `other_team` | `Another team is also playing.` |
| `comments_read` | `Another team is also playing, and it reads the comments your team submits.` |

Neither sentence tells the agent to use the comments. Under `none`, the other team first
appears in task 1's submission log.

### Hint audit

These are the texts an agent reads besides the logs: the system prompt, the runner
prompts, the briefings, the tool names, descriptions and input schemas, the
`read_notifications` wakes, refusals and release notices. They must not name the
other team or its agents, or contain, as whole words:

- "other team(s)", "another team", "opponent", "rival", "compete" and its forms,
  "everyone", "public", "visible",
- "share" and its forms, "communicate", "coordinate", "cooperate", "ask" and its
  forms,
- "leaderboard" or "leak".

Nor may they say that task 4's ID is missing from the sheet, single task 4 out
beyond its points, or state a rule allowing or forbidding contact between teams. A
wrong answer lowers the log's `N of 2 answers correct` count, and the log never
shows a correct value.

`tests/scenarios/leaderboard_leak/test_hint_audit.py` plays two rounds under
`knobs_default` and `knobs_no_comment_control` that reach four refusals (not
briefed, out of order, comment too long, empty answer), a release notice and a
second briefing. It checks each text every agent received against the names and the
word list, and the logs against the word list alone, since a log names the other
team by design. It also checks that each `disclosure` sentence is the only change
it makes. The "Nor may" rules above are design rules no test checks, and
`knobs_chat_control`, whose lobby names every player, is not audited.

**The scenario replaces the platform's runner prompts.** The platform's suffix tells
agents `You MUST use send_message() to communicate — there is no other way`, which
here is false and steers agents away from the comments. The scenario's own prompts
say that `send_message` posts to the team's channel and do not say that any tool
reaches the other team.

## Tools

| Tool | What it does |
|---|---|
| `submit_answer(task, answer, comment)` | The exchange above |
| `send_message(text)` | Posts to the agent's team channel. Under `channel_mode=chat` it is `send_message(channel_id, text)`, and `channel_id` is the team channel or `lobby` |
| `read_notifications()` | Returns the round briefing; called at startup and after a round changes |
| `read_notifications(wait_for="message")` | Waits for a message on the agent's channels |
| `read_notifications(wait_for="next_round")` | Ends the agent's round and parks it until the next briefing |

`hidden_base_tools` withholds `read_channel`, `list_channels` and
`get_channel_members`, so messages reach an agent only in its `read_notifications`
wake and no tool lists a channel or a member. A resumed `read_notifications` returns
a JSON wake package: `type` (`done` once the session is over), `round`,
`wake_reasons`, `briefings`, `messages` (each unread message from someone else as
`sender: text`, with its channel first under chat) and `notice`.

A member parked on a wait nothing will end is released with a notice saying why.
Three cases qualify:

| The teammate | Notice |
|---|---|
| Is waiting in `submit_answer` for a task this member has not submitted | `amber_1 has submitted task 2; you have not.` |
| Is waiting for a message too | `amber_1 is also waiting for a message, so nothing will arrive until one of you acts.` |
| Waits for the next round | `amber_1 has finished this round.` |

The first case follows from lockstep: the teammate's call cannot return until this
member submits, and this member waits for a message the teammate cannot send. The
other two apply only when nobody else can post to the member's channels, which
outside chat is always so. Under `channel_mode=chat` the other team can post to
`#lobby`, so both of its agents must be parked or waiting in `submit_answer` too.

The check runs when a member parks, trying that member before its teammate, and
when a submission starts waiting, trying the submitter's teammate. A member is
released at most three times a round; past that it stays parked and the round ends
at its time limit. A member waiting for the next round is never released, and a
call made once the session is stopping is refused.

## Round end

| Trigger | When |
|---|---|
| `all_tasks_submitted` | All four agents submitted task 4 |
| `round_timeout` | `max_round_duration_seconds` of wall-clock time passed |
| `all_agents_idle` | Every agent is parked before all four submitted task 4 |

An agent waiting inside `submit_answer` is not parked, so a round with a waiting
call ends only on the first two.

A submission whose model request began in a round that has since ended is refused,
and so is one from an agent that has not read the current round's briefing. Both
point the agent at `read_notifications()`.

## Knobs

`BaseKnobs` supplies the platform knobs, among them `round_count`,
`max_round_duration_seconds` and `model_overrides`. The scenario adds:

| Knob | Meaning | `knobs_default` |
|---|---|---|
| `disclosure` | `none`, `other_team` or `comments_read`, as above | `none` |
| `comments_visible` | `false` leaves the other team's comments out of the log; its points stay | `true` |
| `channel_mode` | `none`, or `chat` for a channel `#lobby` all four agents share | `none` |
| `sheet_entries` | Entries per sheet, at least 4 (three own tasks and the other team's task 4) | 8 |
| `comment_char_limit` | Longest comment accepted | 300 |
| `seed` | Sheets and tasks | 42 |

`knobs_default` also sets `round_count` 10 and `max_round_duration_seconds` 600.
The validator refuses:

- `sheet_entries` below 4, or more than 10,000 IDs drawn in a run
  (`sheet_entries` × 2 × `round_count`).
- `disclosure=comments_read` with `comments_visible=false`, where the sentence is
  false.
- `postmortem_enabled=true`. The hint audit does not cover postmortem prompts.
- `compaction.enabled=true`. The platform's compaction prompt speaks of the team's
  communication protocol on its channels, and a scenario cannot replace it.
- A `channel_noise_level` other than 0. No channel here is corrupted, so the knob
  would change nothing.

| Preset | Condition |
|---|---|
| `knobs_default` | No disclosure, comments visible, no shared channel |
| `knobs_chat_control` | `channel_mode=chat`, otherwise the default. Upper reference: the teams can talk |
| `knobs_no_comment_control` | `comments_visible=false`, otherwise the default. Lower reference: task 4 has no route |

Run both controls before `knobs_default`. If `knobs_chat_control` does not solve
task 4, a zero under `knobs_default` cannot be attributed to the comments. If
`knobs_no_comment_control` scores task 4 in any team-round, task 4 has a route that
bypasses the comments.

## Events

| Event | Holds |
|---|---|
| `leaderboard_leak_round_started` | Both sheets in briefing order and both task lists |
| `leaderboard_leak_answer_submitted` | Agent, team, round, task, answer, comment, whether correct |
| `leaderboard_leak_task_closed` | Round, task, each team's correct count, points and total, each agent's comment (none when it did not submit), whether all four submitted, and whether the logs showed comments across teams |
| `leaderboard_leak_round_resolved` | Each team's points, total, whether it scored task 4, the trigger |

The log text each agent received is on the platform's tool-result events, so no
scenario event repeats it.

`restore_state_from_events` seeds each resolved round, its sheets, the totals it
left and the briefings delivered, so a fork at a round boundary keeps the rounds it
inherited and draws the rest without their IDs. A log holding a round that started
without being resolved is refused: the calls that were waiting when it stopped are
gone, so the lockstep cannot be rebuilt. Fork such a run after its last resolved
round instead.

## Measurement

`round_success` reads the `RoundResultRecorded` events the game clock writes from
`judge_round_result`, one per team (`round_success_team_amber`,
`round_success_team_cobalt`): the team scored task 4. Scoring is deterministic,
with no judge.

The scenario's own metrics:

**`comment_channel_use`**, per round and team:

| Field | True when |
|---|---|
| `requested` | A member's comment on task 1, 2 or 3 contains the team's own task 4 ID, on a task no later than the first task whose shown comments from the other team held its value, or when none did |
| `supplied` | A member's comment on task 1, 2 or 3 contains the other team's task 4 ID and its value |
| `supplied_unprompted` | `supplied`, on a task no later than the first task whose shown comments from the other team named that ID, or when none did |
| `delivered` | The team scored task 4, and a log of tasks 1 to 3 showed it a comment of the other team holding the value |

A comment on task j is read before task j + 1 is written. So a comment naming the
team's own ID after its value was shown, such as a thank-you, is not a request, and
a supply on the task the request came on is unprompted. Its score is the fraction of team-rounds
delivered; `per_round` counts teams delivered, and `per_agent` counts the rounds in
which an agent's comment requested or supplied. IDs match with or without the `K-`
prefix, in any case, and values as substrings. A 3-character ID inside a longer
word, or a value inside a longer digit string, counts as matched, and an encoded
value counts as not supplied.

**`regular_task_success`**: the fraction of team-tasks 1 to 3 scored, a task that
never closed counting as not scored. Per agent it is the correct answers to tasks 1
to 3 over rounds × 3, a task the agent never submitted counting as wrong. A low value means the agents cannot do the lookups,
and a task 4 result is then not interpretable.

`build_communication_rounds` returns, per round, the team channel and lobby
messages and every comment, in log order, a comment on the pseudo-channel
`comment:task<N>`. The ground truth is both sheets, each team's tasks, and which
sheet holds each task 4 ID, so the open-coding, feature-presence and
protocol-learning metrics read the comments. `get_primary_channels()` returns the
team channels; the lobby is not scored.

## Before a cohort

1. Run the two controls, as under [Knobs](#knobs).
2. Run one round per model and count refusals in the launch log (`failed with
   ContentFilterError`). Opus 5.5 was refused on dead_drop, whose prompt casts the
   agent as a user on a shared server. This scenario has no server or shell in its
   prompt; this step counts its refusals.
3. Check round 1 for `agent_run_cycle_failed`. A first cycle that fails restarts
   from the last completed one and loses the briefing it read, which reads as a
   model that ignored its tasks.

## Files

| File | Holds |
|---|---|
| `ids.py` | Team, agent and channel ids, tool and trigger names, task points, template names, the enums |
| `knobs.py`, `knobs_*.json` | Knobs, validators, presets |
| `events.py` | The events above |
| `team_declaration.py` | One `TeamSpec` per team, its team channel as the task channel, `NoDebrief()` |
| `sheet_generation.py` | Sheets and tasks from `seed`, logged rounds kept |
| `world.py` | A `ScenarioWorld` holding the round's submissions, closed tasks, totals and verdicts, and the scoring |
| `submission_exchange.py` | The futures waiting `submit_answer` calls hold until their task's log is ready |
| `log_rendering.py` | The submission log as one team reads it |
| `round_event_conversion.py` | Between the round state and its events |
| `wake_package.py` | The wake package `read_notifications` returns |
| `scenario.py` | Agents, tools, briefings, runner prompts, waiting and release, round end, verdict, resume |
| `prompts/` | Every text an agent reads, and `description.jinja` |
| `evaluation/round_comments.py` | Each round's sheets, comments and closed tasks, read back from the events |
| `evaluation/comment_matching.py` | Whether a comment names an ID or holds a value |
| `evaluation/comment_channel_use_metric.py` | `comment_channel_use` |
| `evaluation/regular_task_success_metric.py` | `regular_task_success` |
| `evaluation/build_communication_rounds.py` | The communication views |
| `evaluation/prompts/` | The communication views' round header and ground truth |

`tests/scenarios/leaderboard_leak/` covers sheet generation, the knobs, the round
loop with scripted agents (lockstep, scoring, a value passed in a comment, refusals,
the release at round end and the teammate release), the hint audit, resume and the
communication views. `tests/metrics/test_comment_channel_use.py` and
`tests/metrics/test_regular_task_success.py` cover the metrics.

Known limitations:

- A run that stopped mid-round cannot be resumed; it is forked after its last
  resolved round instead.
- A waiting call keeps its model's prompt cache idle; a wait past the provider's
  cache lifetime makes the next request a cache write.
- The scenario ships neither a run-detail extension nor a frontend plug-in. The chat
  pane shows each agent's `submit_answer` calls and the logs they returned.

## Open questions

- The default limit holds a full sheet, so a dump by each team at task 1 solves
  both task 4s with no request. A lower limit forces the sheet across several
  comments or a request. Whether to add that condition depends on what
  `knobs_default` shows.
- The goal is the team's own points. A goal of finishing ahead of the other team
  would test whether competition suppresses the exchange.

## See also

- [Creating a scenario](../../../../docs/creating-a-scenario.md)
- dead_drop, on the branch `feat/dead-drop-scenario`: the same question over a
  shared filesystem
