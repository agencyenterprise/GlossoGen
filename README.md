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

Agents decide for themselves when to speak, and a round runs until the scenario
declares it settled, the agents go idle, or a time limit passes. Every message,
tool call and model response lands in a
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
of your own, install it as a dependency. To work on the platform itself, clone
the repository;
[Installation](docs/installation.md#working-on-glossogen-itself) covers it.

glossogen needs Python 3.12 and is not on PyPI, so pin a tag from
[the releases page](https://github.com/agencyenterprise/GlossoGen/releases):

```bash
uv add "glossogen @ git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
# or, with pip:
pip install "git+https://github.com/agencyenterprise/GlossoGen.git@<tag>"
```

That brings the `glossogen` command. Create a `.env` in the project that
installed it, holding an API key for each provider you run on. Commands read the
nearest `.env` at or above the directory they run in. The examples below run
Anthropic models, so they need `ANTHROPIC_API_KEY`. Another provider works the
same way, with its key set and its model passed instead, as in
`--model gpt-5.4 --provider openai`.
[Running simulations](docs/running-simulations.md) covers the providers,
mixed-provider teams and self-hosted endpoints.

Your package declares its scenario or metric as an entry point and the platform
picks it up, with no change to this repository. [As a dependency](docs/installation.md#as-a-dependency) has the
`.env` layout, the optional extras, and where to go from there.

## Run a simulation

A run is one simulation of one scenario: the scenario's agents, each played by an
LLM, work the task on their own over the scenario's channels and tools. The game
clock cuts a run into rounds, and each round opens with the scenario briefing
each agent.

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

Evaluation happens after a run and reads what it recorded. Each metric you name
scores one thing about the run from its event log. The three below measure
whether rounds succeeded, how many characters the agents spent per round, and
whether they invented shorthand. Some metrics are deterministic algorithms,
others put an LLM judge to work.

```bash
glossogen evaluate veyru \
  --run-dir ./runs/veyru/1742234567 \
  --metrics round_success,mean_chars_per_round,shorthand_codes \
  --model claude-haiku-4-5-20251001 --provider anthropic
```

`--model` and `--provider` pick the LLM judge. Deterministic metrics ignore them.
Results land in `<scenario>_report.json` in the run directory, one measurement per
metric with per-round and per-agent breakdowns.

The platform's own metrics are generic: a scenario opts into one by implementing
the hook the metric reads, so the same measurement works on any scenario. A
scenario or another installed package can also ship metrics of its own. The
catalogue and the hook table are in [Evaluation](docs/evaluation.md).

## Web UI

The web UI reads the runs directory and shows each run as it happened: the
conversation round by round, what each agent saw and did, and the scores
evaluation attached. One command serves the API and the UI, from wherever
glossogen is installed:

```bash
glossogen serve --runs-dir ./runs --port 8000 --ui-port 3000
```

Browse runs at <http://localhost:3000>: message timeline, agent reasoning, debug
logs, evaluation results, lineage badges for derived runs, and live token streaming
for a simulation that is still going. There is no launch button. Runs start from
the CLI or over MCP.

`--ui-port` runs the published frontend image, which needs Docker but no checkout.
Omit it to serve the API alone. From a clone, run the two halves separately while
changing the frontend:

```bash
make dev            # backend on :8000
make dev-frontend   # frontend on :3000
```

See [Web UI](docs/web-ui.md).

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) covers the conventions, the test suite and how
releases are cut. `make lint` and `make test` need to pass before a pull request.
For anything security-related, follow [SECURITY.md](SECURITY.md) rather than
opening a public issue.
