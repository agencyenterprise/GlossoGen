# GlossoGen

**[Documentation](https://agencyenterprise.github.io/GlossoGen/)** ·
[Quickstart](docs/quickstart.md) · [Scenarios](docs/scenarios.md) ·
[Live demo](https://emergentcomms.ai/demo)

A platform for studying how LLM agents communicate when they have to. Agents are
put in a simulated task where no single one of them holds enough information to
succeed, so nothing gets solved without talking. In most scenarios every character
they send then costs against a fixed per-round budget, and under that pressure they
compress, abbreviate, and invent shorthand. The platform records all of it and
scores it afterwards.

The budget is a knob, and some scenarios ship with it off: `spot_the_difference`
rewards the team that said the least, and `hospital_bed_assignment_privacy` puts
an eavesdropper on the shared channel, so speaking plainly loses the round. [Scenarios](docs/scenarios.md) has
the per-scenario numbers.

Agents decide for themselves when to speak. A game clock advances rounds and
injects scenario events; every message, tool call and model response lands in a
JSONL event log, which is the ledger everything else reads: evaluation metrics,
the web UI, and the flows that rewind a finished run and replay it with a different
agent in one seat.

![Platform overview](images/platform_overview.webp)

Experiments run contained. A simulated agent's only tools are the channel
primitives and the scenario tools served by a loopback-bound MCP server, so it has
no route to another model, to the host system, or to anything outside its own run.
See [Containment of simulated agents](SECURITY.md#containment-of-simulated-agents).

## Install

There are two ways to use glossogen. To write scenarios and metrics in a package
of your own, install it as a dependency; this section shows that. To work on the
platform itself, clone the repository;
[Installation](docs/installation.md#working-on-glossogen-itself) covers it.

glossogen needs Python 3.12 and is not on PyPI, so pin a tag from
[the releases page](https://github.com/agencyenterprise/GlossoGen/releases):

```bash
uv add "glossogen @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
# or, with pip:
pip install "git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
```

That brings the `glossogen` command. Create a `.env` in the project that
installed it, holding `ANTHROPIC_API_KEY`: commands read the nearest `.env` at
or above the directory they run in, and that key is the one variable a run
cannot do without. Your package declares its scenario
or metric as an entry point and the platform picks it up, with no change to this
repository. [As a dependency](docs/installation.md#as-a-dependency) has the
`.env` layout, the optional extras, and where to go from there.

## Run a simulation

A run is one simulation of one scenario: the scenario's agents, each played by an
LLM, work the task on their own over the scenario's channels and tools. The game
clock cuts a run into rounds. Each round opens with the scenario briefing each
agent, a fresh case to stabilize in veyru, and ends judged succeeded or failed,
which is what `round_success` counts later.

```bash
glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  > ./runs/veyru_stdout.log 2>&1 &
```

From a checkout, the same command is spelled
`VIRTUAL_ENV= uv run --no-sync python -m glossogen run ...`, here and below.

All four flags are required, and `--config` names a preset the scenario ships or a
path to a knobs JSON of your own. Output goes to a timestamped directory under
`--runs-dir`.

**A run spends real money against your own keys.** Price one run before launching a
sweep: cost grows faster than round count alone suggests, and nothing in the
platform caps it. See
[Understanding cost](docs/running-simulations.md#understanding-cost).

[Quickstart](docs/quickstart.md) walks one run end to end.
[Running simulations](docs/running-simulations.md) has knobs and presets, per-agent
models, self-hosted endpoints and resuming after a crash.

## Evaluate a run

```bash
glossogen evaluate veyru \
  --run-dir ./runs/veyru/1742234567 \
  --metrics round_success,mean_chars_per_round,shorthand_codes \
  --model claude-haiku-4-5-20251001 --provider anthropic
```

`--model` and `--provider` pick the LLM judge; deterministic metrics ignore them.
Results land in `<scenario>_report.json` in the run directory, one measurement per
metric with per-round and per-agent breakdowns.

Metrics are generic. A scenario opts into one by implementing the hook that metric
reads, so the same measurement works on any scenario, including one installed from
another package. The catalogue and the hook table are in
[Evaluation](docs/evaluation.md).

Wait for the `simulation_ended` event before evaluating. A round-count check fires
one round early and silently drops the last round.

## Web UI

One command serves the API and the UI against a runs directory, from wherever
glossogen is installed:

```bash
glossogen serve --runs-dir ./runs --port 8000 --ui-port 3000
```

Browse runs at <http://localhost:3000>: message timeline, agent reasoning, debug
logs, evaluation results, lineage badges for derived runs, and live token streaming
for a simulation that is still going. There is no launch button; runs start from
the CLI or over MCP.

`--ui-port` runs the published frontend image, which needs Docker but no checkout.
Omit it to serve the API alone. From a clone, run the two halves separately while
changing the frontend:

```bash
make dev            # backend on :8000
make dev-frontend   # frontend on :3000
```

See [Web UI](docs/web-ui.md).

## Extend it

A scenario and a metric are both self-contained, and both can live in this
repository or in a package of your own. To start one in a package of your own,
generate it rather than assembling it:

```bash
glossogen new-scenario reactor_purge --target-dir .
cd reactor-purge && glossogen validate .
pip install -e ".[testing]" && pytest
```

What that writes is a scenario that already runs, which is then yours to edit.
`glossogen validate <dir>` needs no install, so it is the command to keep running
while you edit it.

- [Creating a scenario](docs/creating-a-scenario.md) — the generator, package
  layout, the engine declarations, every optional extension surface, a smoke-test
  recipe and a pre-flight checklist.
- [Creating a metric](docs/creating-a-metric.md) — the `Metric` contract, both
  registration paths, and how to run one.
- [Testing a scenario](docs/testing-a-scenario.md) — `glossogen.testing`: the
  contract checks, the scripted round loop, and why the harness controls the
  clock rather than waiting on it.

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers the conventions, the test suite and how
releases are cut. `make lint` and `make test` need to pass before a pull request.
For anything security-related, follow [SECURITY.md](SECURITY.md) rather than
opening a public issue.
