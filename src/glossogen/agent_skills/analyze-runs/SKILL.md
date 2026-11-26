---
name: analyze-runs
description: Analyze a group of glossogen runs. Check that the runs match the plan, have subagents read what the agents wrote, find unusual communication or behaviour, check every claim against the event logs, and write a findings file. Use when someone asks to analyze runs or an experiment, look for strange protocols, explain why one setting did better than another, or compare models or knob values.
---

# Analyzing glossogen runs

Terms used here:

- **Agents** are the agents in a run. **Subagents** are the Claude sessions that you start while you follow this skill.
- A **condition** is one setting of what the experiment varies, such as one knob value or one model.
- A **code** is any convention that agents use to carry meaning, such as a table of letters for objects, a fixed message layout, or a standard encoding like hexadecimal.
- A round's **ground truth** is what the agents had to find or do in that round, as the scenario recorded it in the log.
- The **behaviour list** is [references/behaviour-list.md](references/behaviour-list.md). It holds kinds of behaviour to check for after the first reading.
- The **findings file** is the file that the analysis ends with. Its format is in [references/findings-file.md](references/findings-file.md).

Run `glossogen` the way the project runs it, for example `uv run glossogen`. [references/run-data.md](references/run-data.md) lists what a run directory holds and which command reads each part.

## 1. Agree on the question and the runs

Ask the researcher for anything that is missing:

- the question that the analysis answers, and the result that the researcher expects, if any;
- the runs of each condition, as labels, knob values or run ids;
- earlier results that this analysis builds on, so that a finding can be compared with them;
- the folder for the transcripts and the findings file.

For runs on a remote glossogen server, connect Claude Code to that server's MCP endpoint (see the glossogen docs on MCP integration). Its `export_run_artifacts` tool returns a link to a tar.gz of a run's directory. Extract each one into `<runs dir>/<scenario>/<run id>/`, and follow the steps below on the local copy.

Before you start more than a few subagents, tell the researcher how many you will start, on which model, and about how many tokens they will read. For English text, a transcript's character count divided by 4 approximates its tokens. Use a smaller model, such as Haiku or Sonnet, for subagents that read transcripts. Keep the larger model for merging and checking.

## 2. Check what ran

For each run, read what the log recorded, not the labels alone:

- `simulation_started`: the knob values (`scenario_config`) and the glossogen version and commit (`glossogen_build`);
- `agent_registered`: each agent's model, provider and system prompt;
- `labels.json`, and the manifest of a derived run, such as a fork (run-data.md lists them).

`glossogen export --out <dir> --frames run_level` writes a table with one row per run, its knob values and its models. Compare every run with the planned runs: the model of each agent, the knob values, the seed, the round count and, for a derived run, its source. List each mismatch and each duplicate run, and ask the researcher whether to leave those runs out.

When the conditions were run at different times, list every difference between them besides the one under study. Compare the glossogen versions, the system prompts, the judge model (the model that scores rounds, when the scenario has one) and the agents' model settings in `scenario_config`. Each difference goes in the findings file's limits.

## 3. Learn the scenario

Render one run first:

```bash
glossogen transcript <scenario> --run-dir <run dir> --out-dir <work dir>/<run id>
```

The first line of `round_00.txt` gives the path of the scenario's README in the installed glossogen, which can be another version than the run's `glossogen_build`. Read the README, but leave its section called "Analyzing runs", if it has one, for step 6.

From `round_00.txt` and `round_01.txt`, write down:

- what each agent is told, and what it can see that its partner cannot;
- what carries information between agents: a channel, moves, actions or shared files;
- what the scenario limits, such as characters, messages or moves;
- where the log records each round's ground truth, such as a scenario event at the start of the round or the briefings.

You need these notes in step 7, to tell a code that an agent made up apart from information that both agents already had.

## 4. First reading, without the behaviour list

Do not open the behaviour list yet. Keep it, your own guesses and earlier findings out of every brief. Subagents then report only what they read in the runs.

1. Render every run with `glossogen transcript ... --out-dir`.
2. Start one subagent per run. When a run's transcript is over about 100,000 tokens, start one subagent per range of rounds instead, such as rounds 1 to 5 and rounds 6 to 10. Use the first-reading brief in [references/subagent-briefs.md](references/subagent-briefs.md).
3. Each subagent returns observations: run, round, agent, a quote, and what is unusual about it.
4. Merge the observations into candidate behaviours: behaviours that the first reading suggests. Keep each observation that subagents reported in more than one run, and each one-off that would be new for the scenario. Give each candidate a short name and a definition of one or two sentences.

## 5. Count each behaviour

Start subagents with the counting brief. Each one reads every message of its runs against the written definitions, and returns one row per occurrence: run, round, agent, behaviour and quote.

- Do not use a regular expression, a keyword list or an `if` on what agents wrote. This also holds for choosing which messages a subagent reads. Agents phrase one idea in many ways, and they repeat words from their own prompt, so a keyword count both misses cases and counts false ones.
- Values that the platform records as event fields are data: round outcomes, character counts, moves, tokens. Compute those with code.
- Give a second subagent the same definitions and about one run in five. For each behaviour, report the rows that both subagents returned, the rows that only one of them returned, and the number of runs in the sample. When fewer than about four rows in five are shared, sharpen the definitions and count again. Settle the remaining disagreements yourself from the transcript.
- Check a sample of the rows against the transcripts yourself.

## 6. Check the behaviour list

Now read the behaviour list and the README's "Analyzing runs" section. Start one subagent per run with the brief for checking the behaviour list. Each one checks its run for each listed behaviour that step 4 did not find. Its results go in their own section of the findings file. Check each one in the transcript before you use it.

## 7. Check every claim

Check every claim that the logs can confirm or refute. A claim about why agents did something often cannot be checked in the logs. Mark it as an interpretation in the findings file.

- **Codes.** When agents used an encoding, decode their messages with a script and compare the result with the round's ground truth. Report how many messages decode correctly. Before you say that runs share a code, compare the codes run by run.
- **Information.** For each claim that an agent passed something to another agent, confirm that the receiving agent did not already have it from its briefing, its view of the world or a shared file.
- **Causes.** An agent's explanation of an event is not its cause. Find the event in the log. A wrong answer can follow a partner's typo rather than a misunderstanding.
- **Refutation.** Give the strongest claims to a new subagent with the refutation brief. Drop a claim that does not hold. Narrow a claim that holds in part to the part that holds.
- **Numbers.** Recompute every number with a script from the counted rows or the event logs. Record the command next to the number.

## 8. Compare conditions

- Compare a model with itself under each condition. Give both values and the number of runs behind each, for example "72% over 15 runs and 49% over 15 runs". Do not give only the difference in points.
- To summarise many models, first average each model's runs. Then average those model averages, so that each model counts once, and give the lowest and the highest model average. Say which average you used.
- The expected direction is the result that the researcher expected in step 1. Without one, use the direction that most models show. Count the models and conditions that went the other way. Each of these cases is a finding.
- A run without a measurement is missing, not zero. Leave it out of the average and report how many runs are missing. A measured 0 stays in.
- Compare each finding with the earlier results from step 1. Drop a finding that repeats one of them, or state only the part that is new. Call a behaviour new for this scenario only after you checked the README and the earlier results.

## 9. Show how the codes formed

For each condition, show:

- a grid with one row per run and one column per round, where each cell names the kind of message in that round, such as plain English, a letter code or hexadecimal;
- in the same grid, the round in which an agent proposed each code, and the round in which its partner first used it;
- the number of runs that used each code, and the round in which it first appeared;
- the same rounds quoted side by side from runs of different conditions;
- one decoded example of each code, checked against the round's ground truth.

When the agents of a condition built no code, say so, with the number of runs.

## 10. Write the findings file

Follow [references/findings-file.md](references/findings-file.md). Write one fact per sentence. Define each term where it first appears and keep that term. Give the full model names. Every "all", "none", "never" or "only" carries its count and denominator. Next to each measure, say what it misses and what it over-counts.
