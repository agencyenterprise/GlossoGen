# Analyzing runs with Claude Code

glossogen ships a Claude Code skill called `analyze-runs`. The skill gives the steps that Claude follows to analyze a group of runs. In short, Claude:

- agrees on the question and on the runs of each condition with you;
- checks each run's recorded models and knob values against the plan;
- has subagents, other Claude sessions, read every transcript, first without a list of expected behaviours;
- counts each behaviour against a written definition, with a quote for each count;
- checks every claim against the event logs;
- writes a findings file.

The skill's `SKILL.md` gives the full steps.

The skill is separate from `glossogen analyze`, which groups runs and summarises their metrics.

## Install the skill

In a project that installs glossogen, copy the skill into the project's skills folder:

```bash
glossogen install-skill
```

The command writes `.claude/skills/analyze-runs/`. `--target-dir` writes somewhere else, such as `~/.claude/skills` for every project. The copy comes from the installed glossogen. After an upgrade, run the command again with `--replace` to get the new version's copy. Without `--replace`, the command refuses to overwrite a skill folder that already exists.

In a clone of the glossogen repository, `.claude/skills/analyze-runs` links to the skill's source, so Claude Code finds it without the command.

## Use it

Ask Claude Code a question about your runs, for example "analyze the runs labelled `budget_sweep`: do the codes that agents build at budget 150 differ from those at 800?". Claude can load the skill when a request matches the skill's description, and `/analyze-runs` loads it directly. Claude asks for anything that the analysis needs and the request leaves out: the question, the runs of each condition, and earlier results to compare with.

The skill tells Claude to say how many subagents it will start, on which model, and about how many tokens they will read, before it starts them.

## What the skill reads

### Transcripts

`glossogen transcript` prints a run's event log as plain text, round by round:

```bash
glossogen transcript veyru --run-dir runs/veyru/1777638061
glossogen transcript veyru --run-dir runs/veyru/1777638061 --out-dir transcripts/1777638061
```

`--out-dir` writes one file per round: `round_00.txt` holds the setup and each agent's system prompt, and `round_NN.txt` holds round NN. The first line gives the path of the scenario's README in the installed glossogen.

A transcript keeps what each agent was told, wrote, called and received, in log order: briefings, reasoning text, messages, tool calls with their arguments, and tool results. It leaves out event ids, timestamps, token counts and the `agent_resumed` events. It also leaves out the `tool_call_invoked` events, because the model response before each one already lists its tool calls. It keeps a `wait_registered` event only when the agent gave a reason for waiting. Other events, including the scenario's own events, are printed with their fields as JSON. Under channel noise, a message line shows the text that the channel delivered, and the sender's `send_message` call shows what the sender wrote.

### The scenario's notes

A scenario's README can hold a section called "Analyzing runs". The section lists what someone reading the runs can misread, and the ways that agents can win a round without the behaviour that the scenario tests. [Creating a scenario](creating-a-scenario.md#notes-for-analyzing-runs) says what goes in it.

### The code that wrote a run

The `simulation_started` event records `glossogen_build`:

| Field | Holds |
|---|---|
| `version` | the installed glossogen version |
| `git_commit` | the commit that a git install came from, or the checkout's `HEAD` for an editable install; null for an install that records no commit, such as one from a wheel |
| `has_uncommitted_changes` | whether an editable checkout had changes under `src/` that the commit does not hold, untracked files included; false for a git install; null when no commit is known |

A derived run, such as a fork or an agent replacement, records the glossogen that derived it. It copied its first rounds from its source run, and the source run's log records the glossogen that played them. A run continued with `--resume` keeps the build that started it. A log written before glossogen recorded the field has none, and its transcript says "not recorded in this log".
