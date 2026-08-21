# Quickstart

Run a simulation, read the log it wrote, and score it. These are the same commands
a study uses.

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

`warehouse_robot_recovery` puts three agents around a stopped robot, and none of
them can see the whole problem. The floor associate is the only one who can see the
machine, the robotics engineer holds the recovery procedures, and the fleet safety
coordinator holds the constraints. They share one radio channel, which costs a
character budget and is the only channel scored. The default preset also gives them
a free debrief channel between rounds.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run warehouse_robot_recovery \
  --model claude-haiku-4-5-20251001 --provider anthropic \
  --runs-dir ./runs \
  --config knobs_default \
  round_count=3 \
  > ./runs/quickstart.log 2>&1 &
```

On an installed package the same command is `glossogen run warehouse_robot_recovery ...`.

| Argument | What it does |
|---|---|
| `--model`, `--provider`, `--runs-dir`, `--config` | All four are required. Nothing picks a configuration for you. |
| `--config knobs_default` | Names a preset the scenario ships. A path to a JSON file of your own works here too. |
| `round_count=3` | A knob override: one field of the preset changed without copying it. The preset's own value is 15. |

Cost climbs faster than the round count, because every round carries the whole
conversation before it. Price one run before launching a sweep;
[Understanding cost](running-simulations.md#understanding-cost) has the details.

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

Expect many more turns than messages. Most of a turn is reading notifications and
calling tools rather than speaking.

| Event | What it records |
|---|---|
| `message_sent` | An agent speaking on a channel |
| `injection_delivered` | The scenario telling one agent what happened this round |
| `world_event_delivered` | The world answering an agent's action |
| `round_advanced` | Round N starting |
| `simulation_ended` | The run finishing, and the only signal that it has |

Nothing is mutated after the fact, so a byte offset into this file is a stable
address. That is what lets a finished run be replayed from any round.

## 4. Score it

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen evaluate warehouse_robot_recovery \
  --run-dir "$RUN" \
  --metrics round_success,mean_chars_per_round,mean_chars_per_message,round_ended_idle,round_ended_timeout \
  --model claude-haiku-4-5-20251001 --provider anthropic
```

Every metric in that list is deterministic, so this run costs nothing: the report's
`evaluation_cost.estimated_cost_usd` comes back `0.0`. `--model` and `--provider`
choose the LLM judge, which only the judge-backed metrics use. Each metric logs its
score as it finishes, and the report lands at
`<run>/warehouse_robot_recovery_report.json`.

Read `round_ended_idle` against `round_ended_timeout` before you read any throughput
number. They count how each round ended, agents going idle or the wall clock running
out, and a throughput number taken from rounds that hit the clock is measuring the
clock.

Metrics are generic. A scenario opts into one by implementing the hook that metric
reads, so the same measurement works across scenarios, including scenarios installed
from other packages. Adding `shorthand_codes` or `language_repetition` to that list
puts a judge model to work and spends real money.
[Evaluation](evaluation.md) has the full catalogue and which hook each metric reads.

## Where next

- **Pick a different scenario** — [Scenarios](scenarios.md) for what ships and which
  to start with.
- **Write your own** — [Creating a scenario](creating-a-scenario.md), then
  [Testing a scenario](testing-a-scenario.md) for the scripted harness.
- **Understand the numbers** — [Evaluation](evaluation.md) for the catalogue,
  [Communication metrics](communication-metrics.md) for how the language measures
  read together.
- **Replay a finished run** — [Agent swaps and resume](agent-swaps.md), for
  restarting a run from a chosen round with one agent replaced. This is how the
  platform answers "could a fresh agent pick up the protocol from here" by
  experiment rather than by asking a judge.
