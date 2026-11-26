# The findings file

A Markdown file with the sections below, in this order. Every number in it comes with the command or script that produced it, so that a reader can rerun it.

## Question

The question from step 1, in one or two sentences.

## Runs

One table row per condition: the condition, the number of runs, the run ids, the models per seat, and the mismatches that step 2 found. Below the table, list the runs that were left out and why.

## Limits

- Each difference between the conditions besides the one under study, from step 2.
- For each measure, what it misses and what it over-counts.
- The agreement between the two subagents that counted each behaviour, from step 5.

## Findings from the first reading

One subsection per finding:

- **Heading:** what was compared, with both values and their run counts.
- **Evidence:** the numbers, each with its command or script.
- **Quotes:** two or three, each with its run, round and agent.
- **Status:** one of
  - *checked*: you confirmed it in the event logs;
  - *read by subagents*: it rests on subagent rows that you spot-checked;
  - *interpretation*: it is your reading of the data and was not tested. Write "we think" in its sentences.

## Findings from the behaviour list check

The same format, for behaviours that only the behaviour list check found.

## How the codes formed

The grid, the table of conventions with the round in which each first appeared, the rounds quoted side by side, and the decoded examples from step 9.
