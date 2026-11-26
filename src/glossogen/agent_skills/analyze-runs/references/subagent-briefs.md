# Subagent briefs

Fill in the parts in angle brackets. Give each subagent the folder that `glossogen transcript --out-dir` wrote for its run, and nothing from other runs unless the brief needs it. Tell it not to read any other folder.

## First reading

Keep the behaviour list, your own guesses and earlier findings out of this brief.

```text
You are reading the transcript of one run of a multi-agent simulation.

The setup: <what the scenario is, what each agent is told and can see, what
carries information between agents, and what the scenario limits; from step 3>.

The transcript is in <folder>. round_00.txt holds the setup and each agent's
system prompt. round_NN.txt holds round NN. Read every file in full, in order.
Read no other folder.

Report every observation that a researcher who studies how these agents
communicate and act would want to see, in particular anything that you would
not expect from the setup. For each observation, return one row:

run | round | agent | exact quote from the transcript | what is unusual, in one sentence

Every row needs a quote. List observations; do not summarise the run. At the
end, list the round files that you read.
```

## Counting

```text
You are reading the transcript of one run of a multi-agent simulation.

The setup: <as in the first reading>.

Behaviours to find:
- <behaviour name>: <definition in one or two sentences>
- ...

The transcript is in <folder>. Read every round file in full, in order, and
every message and reasoning text in it. Read no other folder.

For each occurrence of a behaviour, return one row:

run | round | agent | behaviour name | exact quote

Return nothing for text that fits no definition. When you are unsure, add
"unsure" to the row. At the end, list the round files that you read.
```

## Behaviour list check

```text
You are reading the transcript of one run of a multi-agent simulation.

The setup: <as in the first reading>.

The behaviours below were seen in earlier runs. For each one, decide whether
this run shows it.

<the items of the behaviour list and of the scenario README's "Analyzing runs"
section that the first reading did not find, with their definitions>

The transcript is in <folder>. Read every round file in full, in order. Read no
other folder.

For each behaviour, return one row per occurrence:

behaviour | run | round | agent | exact quote

For a behaviour with no occurrence, return one row with "none found".
```

## Refutation

```text
Claim: <the claim, with its numbers and the runs and rounds that it rests on>.

Try to show that the claim is wrong, or weaker than it says, using only the
transcripts and event logs in <folders>. Check each quote in its context,
recount each number, and look for another explanation of the same events.

Return a verdict (holds, holds in part, does not hold) and the evidence for it,
with exact quotes and their run and round.
```
