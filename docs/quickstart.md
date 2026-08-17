# Quickstart

Run a simulation, read the log it wrote, score it, then generate a scenario of your
own and validate it. These are the same commands a study uses.

Read [the README](../README.md) first for what the platform is for. This page
assumes only that.

## 1. Install

Needs Python 3.12, Node ≥ 22, [uv](https://docs.astral.sh/uv/), make and git.

```bash
make install                 # backend and frontend
make install-metrics         # add this if you will run the ML-backed metrics
cp .env.example .env         # then set ANTHROPIC_API_KEY
```

Postgres is optional: leave `DATABASE_URL` unset and the runs index comes from the
filesystem. [Installation](installation.md) has the rest, including the weasyprint
system libraries and what each optional extra buys you.

## 2. Run a simulation

`warehouse_robot_recovery` has three agents, none of whom can see the whole
problem, and one channel between them that costs a character budget to use.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run warehouse_robot_recovery \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  --runs-dir ./runs \
  --config knobs_default \
  round_count=3 \
  > ./runs/quickstart.log 2>&1 &
```

`--model`, `--provider`, `--runs-dir` and `--config` are all required: nothing
picks a configuration for you. `round_count=3` is a knob override, which is how you
change one field of a preset without copying it. The preset's own value is 15.

**What this costs.** Three runs of exactly this shape, measured:

| Run | Wall clock | Cost | `round_success` |
|---|---|---|---|
| 1 | 0.7 min | $0.16 | 0/3 |
| 2 | 2.5 min | $0.34 | 1/3 |
| 3 | 2.7 min | $0.34 | 0/3 |

**The cost is not linear in rounds, or in model.** `container_yard_stacking`, also
three agents, costs $37 to $50 for a 15-round run on `claude-opus-4-7`, because
every round carries the whole conversation before it. Price one run before launching
a sweep; [Understanding cost](running-simulations.md#understanding-cost) has the
details.

**One round of nine succeeded.** `claude-haiku-4-5` is weak on this scenario rather
than hopeless at it, and three identical configurations scored 0/3, 1/3 and 0/3. So
a verdict is recorded per round rather than once per run, and a comparison needs
replications: "the agents did not solve it" and "the scenario is unsolvable" are
different findings, and one run cannot separate them. For runs that solve more of
it, put `claude-sonnet-4-6` or `gpt-5.4` on the agents and keep haiku as the judge.

If your environment has no key for the provider you named, the run is refused at
the command line rather than starting and failing once the clock has run out.

Wait for the run to finish before scoring it:

```bash
grep -c '"simulation_ended"' ./runs/warehouse_robot_recovery/*/warehouse_robot_recovery.jsonl
```

Wait for that event, not for a round count. `round_advanced` to round N fires when
round N *starts*, so counting rounds tells you a run is done while its last round
is still going, and you score a run missing its final round.

## 3. Read what it recorded

Everything downstream reads one file: the web UI, every metric, and every flow that
rewinds a finished run.

```bash
RUN=./runs/warehouse_robot_recovery/<timestamp>
VIRTUAL_ENV= uv run --no-sync python -c "
import collections, json, sys
kinds = collections.Counter(json.loads(l)['event_type'] for l in open(sys.argv[1]) if l.strip())
for kind, count in kinds.most_common(8): print(f'{count:5} {kind}')
" "$RUN/warehouse_robot_recovery.jsonl"
```

For the run in the table above:

```
  154 llm_response_received
  153 tool_call_invoked
  153 tool_result_received
   22 message_sent
   21 world_event_delivered
   18 injection_delivered
    3 agent_registered
    3 round_advanced
```

The agents took 154 turns to send 22 messages, because most of a turn is reading
notifications and calling tools rather than speaking. `injection_delivered` is the
scenario telling each agent what happened this round; `world_event_delivered` is the
world answering their actions. Nothing is mutated after the fact, so a byte offset
into this file is a stable address, which is what lets a finished run be replayed
from any round.

## 4. Score it

Metrics are generic. A scenario opts into each one by implementing the hook that
metric reads, so the same measurement works across scenarios and on scenarios
installed from other packages.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate warehouse_robot_recovery \
  --run-dir "$RUN" \
  --metrics round_success,mean_chars_per_round,mean_chars_per_message,round_ended_idle,round_ended_timeout \
  --model claude-haiku-4-5-20251001 --provider anthropic
```

Every metric in that list is deterministic, so this run cost nothing: the report's
`evaluation_cost.estimated_cost_usd` comes back `0.0`. `--model` and `--provider`
choose the LLM judge, which only the judge-backed metrics use.

The report lands at `<run>/warehouse_robot_recovery_report.json`:

```
round_success                  0.00  fraction of rounds succeeded (0/3)
mean_chars_per_round         187.33  chars/round
mean_chars_per_message        46.83  chars/message
round_ended_idle               1.00  rounds ended via all_agents_idle (out of 3)
round_ended_timeout            0.00  rounds ended via round_timeout (out of 3)
```

`round_ended_idle` at 1.00 says every round ended because the agents stopped
talking rather than because the clock ran out, so they had time they did not need.
Had that been `round_ended_timeout`, the throughput numbers would be measuring the
time limit rather than the agents.

The judge-backed metrics are where the language findings come from. Add
`shorthand_codes` or `language_repetition` to that list and the same command
spends real money on the judge model. [Evaluation](evaluation.md) has the full
catalogue and which hook each metric reads.

## 5. Write a scenario of your own

Generate it rather than copying one. What the scaffold writes already runs, so
your first edit is to something that works.

```bash
glossogen new-scenario reactor_purge --target-dir ~/scenarios
cd ~/scenarios/reactor-purge
glossogen validate .
```

```
reactor_purge: 34 checks passed across 1 preset(s): knobs_default
```

Pointed at a directory, `validate` needs no install, so it is the command to keep
running while you edit. It builds your scenario from every preset it ships and checks
what Python cannot: agents claiming channels that do not exist, `get_agent_roles`
disagreeing with the agents actually built, every round's injection rendering, its
event types against the platform's, and the package around it. It needs no API
key.

Then install it and run its tests, which drive the real round loop with the model
replaced by a script, so they cost nothing and wait for nothing:

```bash
pip install -e ".[testing]"
pytest
```

Now it is a scenario like any other, including in the runs directory of the
platform you already have:

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run reactor_purge \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  --runs-dir ./runs --config knobs_default round_count=2 \
  > ./runs/reactor_purge.log 2>&1 &
```

[Creating a scenario](creating-a-scenario.md) is the reference for what each file
in that package is responsible for. Read it once you have broken something.

## 6. Change one thing

Two edits, to see which knobs move which numbers.

**A knob.** Re-run step 2 with `max_round_duration_seconds=30` and watch
`round_ended_timeout` go up and `mean_chars_per_round` go down: the agents are now
being cut off rather than finishing. That pair is the first thing to check
whenever a throughput number looks strange.

**A prompt.** Every prompt is a Jinja template under the scenario's `prompts/`,
never a string in Python. Edit one, then:

```bash
make lint-server    # checks your template parses, and that nothing else broke
```

Rendering is strict: a variable the scenario does not pass raises rather than
silently becoming an empty string. A misspelled name once produced a budget line
with no number in it, and a run that looked plausible for fifteen rounds.

## Where next

- **Writing a scenario properly** — [Creating a scenario](creating-a-scenario.md),
  then [Testing a scenario](testing-a-scenario.md) for the scripted harness.
- **Understanding the numbers** — [Evaluation](evaluation.md) for the catalogue,
  [Communication metrics](communication-metrics.md) for how the language measures
  read together.
- **Replaying a finished run** — [Agent swaps and resume](agent-swaps.md), for
  restarting a run from a chosen round with one agent replaced. This is how the
  platform answers "could a fresh agent pick up the protocol from here" by
  experiment rather than by asking a judge.
