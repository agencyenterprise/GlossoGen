# Running simulations

A run is one simulation of one scenario. Agents connect to a loopback-bound MCP
server, the scenario briefs each agent as a round opens, and every event lands in
a JSONL log that later commands read back. A round runs until the scenario
declares it settled, every agent goes idle, or the time limit passes. The game
clock watches for whichever comes first and opens the next round.

```bash
glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  > ./runs/veyru_stdout.log 2>&1 &
```

From a checkout, spell each command
`VIRTUAL_ENV= uv run --no-sync python -m glossogen ...`.

| Flag | Does |
|---|---|
| `--model` | Model identifier, required. The default for every agent, see [per-agent models](#per-agent-models) |
| `--provider` | `anthropic`, `openai`, `google-gla`, `ollama`, `self-hosted`; required. Also the default for every agent |
| `--runs-dir` | Root directory for run output. Required unless `--resume` is given, which names the directory itself |
| `--config` | A preset the scenario ships (`knobs_default`), or a path to a JSON file of your own; required |
| `--max-agent-turns` | Ceiling on agentic turns per agent (default 200) |
| `--resume` | Path to an existing run directory to continue |
| `--group-slug` | Tenant group that owns the run (default `local`) |

Output goes to a timestamped directory the CLI creates:
`<runs-dir>/<scenario>/<unix_timestamp>/`. Its layout is described under
[Run Storage](../Architecture.md#run-storage). Run simulations in the background
and pipe output to a log. The [web UI](web-ui.md) is the comfortable way to watch
one: the run list shows its status and the round it reached, and the run page
streams messages live until it completes.

## Configuration

The `run` subcommand takes a base config and trailing `key=value` overrides,
Hydra-style. Values parse as JSON, so `round_count=20` is an int, `enabled=true` a
bool, and `name=alice` stays a string.

```bash
glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_intern \
  max_round_duration_seconds=120 round_count=20
```

Each scenario ships one or more presets next to its code (`knobs_default.json` and
friends) and publishes a JSON Schema for its knobs. The [web UI](web-ui.md) and the
[MCP tools](mcp-integration.md) read both, so a preset is discoverable without
reading the source.

`--config` takes a preset name without the `.json`, which is what makes one command
work from a checkout and from an installed package alike. A path wins when the
argument is one, so an experiment can keep its knobs JSON outside any package. The
flag is required, so every run is launched under a configuration someone chose.
Each launch logs what it resolved to.

```
Scenario knobs from preset 'knobs_default'
```

**Knobs can depend on each other.** A scenario's knobs model may carry cross-field
validators that reject an override which looks fine on its own, so when overriding
one knob, override every knob the scenario validates against it. Validation happens
before the run claims a directory: a rejected config leaves no run behind, and the
error lands in that launch's stdout log.

### Per-agent models

`--model` and `--provider` set the default every agent runs under.
`model_overrides` in the config replaces the pair for the agents it names, keyed
by `agent_id`.

```json
{
  "round_count": 12,
  "model_overrides": {
    "stabilization_engineer": {"model": "gpt-5.4", "provider": "openai"},
    "field_observer": {"model": "claude-opus-4-6", "provider": "anthropic"}
  }
}
```

The CLI also accepts them as dot-notation overrides, normalized into the same
field, which is how a sweep varies one seat without writing a config per cell:

```bash
glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  agents.field_observer.model=claude-opus-4-7 \
  agents.stabilization_engineer.model=gpt-5.4 \
  agents.stabilization_engineer.provider=openai
```

| Rule | Detail |
|---|---|
| An override must name a `model` | `provider` is optional and falls back to `--provider`, so `field_observer` above stays on Anthropic. Moving an agent to another provider takes both lines |
| The flags stay required even when every agent is overridden | No agent runs under them, but `--provider` is still the fallback for an override that names only a model, so set both to real values rather than placeholders |
| The launch check reads the resolved pairs | A run whose every agent is on `openai` needs no credential for the `--provider` on the command line. It needs a key for every provider some agent resolved to, plus the scenario's judge, which is its own knob (`judge_provider`) |

### Self-hosted and local models

`--provider self-hosted` points pydantic-ai at any OpenAI-compatible
chat-completions endpoint. `SELF_HOSTED_BASE_URLS` is a JSON map from model name to
`/v1` URL, so several self-hosted models coexist. `SELF_HOSTED_API_KEY` is the
bearer token shared across them. In the `.env`:

```bash
SELF_HOSTED_BASE_URLS='{"meta-llama/Llama-3.3-70B-Instruct": "https://my-llama.example.com/v1", "Qwen/Qwen3-32B": "https://my-qwen.example.com/v1"}'
SELF_HOSTED_API_KEY=<the token your servers were started with>
```

`--model` names a key of that map:

```bash
glossogen run veyru \
  --model meta-llama/Llama-3.3-70B-Instruct --provider self-hosted \
  --runs-dir ./runs \
  --config knobs_default
```

Deploying on Modal, and running locally with Ollama or MLX, are covered in
[Self-hosted models](local-inference-vllm-mlx.md). Pricing is keyed by
literal model name in
[token_pricing.py](../src/glossogen/token_pricing.py). Add an entry there for a
model it does not know.

**Watch the context budget.** Self-hosted models are served at a small fixed
context, and `input + agent_max_tokens` must stay under it or the server rejects the
call and the run stalls. The per-cycle output cap is the `agent_max_tokens` knob
(default `16384`), not `LLM_MAX_TOKENS`, which caps the platform's own judge and
probe calls and never touches an agent. For swap and resume runs, where a
reconstructed history keeps growing, set `agent_max_tokens: 2048` in the config.

## Continuing a run

`glossogen run --resume <run-dir>` continues an interrupted run inside that same
directory: no new run directory is created, and new events append to the run's
existing JSONL. Channel messages and scenario state are rebuilt from the log, and
each agent gets its history back. Pass the `--config`
the run was launched with: nothing compares it against what the run recorded, and
a knob changed midway leaves one log produced under two configurations.

```bash
glossogen run <scenario> \
  --model <model> --provider <provider> \
  --resume ./runs/<scenario>/<timestamp> \
  --config <config> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

The clock reopens the last round the log recorded, the one that never finished,
and runs to the config's `round_count`.

This is for a run that stopped before it was done, whether it crashed, was
killed, or lost its machine. For a run that *finished*, resuming in place would
replay its final round, which already has a verdict. Use
[`fork-at-round`](agent-swaps.md#fork-at-a-round-no-replacement) instead: it
keeps rounds 1..N complete, plays round N+1 onward in a fresh run directory,
leaves the original untouched, and can run further than the source did. To fork
a finished run with a different agent in one seat, see
[Agent swaps and forks](agent-swaps.md).

## Understanding cost

A run spends real money against **your own** provider keys. An agent takes many
turns per round, and every turn is an API call carrying the whole conversation so
far, so cost grows faster than the round count alone suggests.

The knobs that drive spend, roughly in order of impact:

| Knob | Effect |
|---|---|
| `round_count` | Rounds per run, the main multiplier |
| Model choice | The largest single factor. The models priced in `token_pricing.py` span 25× on input tokens and 20× on output, from `gpt-5.4-nano` to the Opus tier |
| `max_round_duration_seconds` | Ceiling on how long agents keep talking before a round is cut off |
| `agent_max_tokens` | Per-turn output cap (default `16384`) |
| Number of agents | Each one is an independent conversation |
| `--probe-replicas` | Evaluation only: multiplies probe calls per agent per question |

What a run itself spent is on its last event: `simulation_ended` carries
`total_cost_usd`, priced from
[token_pricing.py](../src/glossogen/token_pricing.py). The web UI reads it, and so
does `grep`:

```bash
grep '"simulation_ended"' ./runs/<scenario>/<timestamp>/<scenario>.jsonl
```

The `evaluation_cost` block in the evaluation report is a different number: what the
judge and probe calls of `glossogen evaluate` spent. A run scored with deterministic
metrics only has `evaluation_cost.estimated_cost_usd` of `0.0` however much the
simulation cost.

Nothing in the platform caps spend. Billing alerts and per-key limits with your
provider are the only ceiling that holds.

## Next

- [Evaluation](evaluation.md) — scoring a finished run
- [Agent swaps and forks](agent-swaps.md) — forking a run at a chosen round boundary
- [Scenarios](scenarios.md) — what ships in the box
- [Creating a scenario](creating-a-scenario.md) — writing your own
