# Running simulations

A run is one simulation of one scenario. Agents connect to a loopback-bound MCP
server, a game clock advances rounds and delivers scenario injections, and every
event lands in a JSONL log that later commands read back.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  > ./runs/veyru_stdout.log 2>&1 &
```

On an installed package the same command is `glossogen run veyru ...`.

| Flag | |
|---|---|
| `--model` | Model identifier, required. The default for every agent, see [per-agent models](#per-agent-models) |
| `--provider` | `anthropic`, `openai`, `google-gla`, `ollama`, `self-hosted`; required. Also the default for every agent |
| `--runs-dir` | Root directory for run output, required |
| `--config` | A preset the scenario ships (`knobs_default`), or a path to a JSON file of your own; required |
| `--max-agent-turns` | Ceiling on agentic turns per agent (default 200) |
| `--resume` | Path to an existing run directory to continue |
| `--group-slug` | Tenant group that owns the run (default `local`) |

Output goes to a timestamped directory the CLI creates:
`<runs-dir>/<scenario>/<unix_timestamp>/`. Its layout is described under
[Run Storage](../Architecture.md#run-storage). Run simulations in the background
and pipe output to a log. Check progress by reading that log, or by counting
`round_advanced` events in the JSONL.

## Configuration

The `run` subcommand takes a base config and trailing `key=value` overrides,
Hydra-style. Values parse as JSON, so `round_count=20` is an int, `enabled=true` a
bool, and `name=alice` stays a string.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
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
flag is required: the JSONL records what a run was launched with, and a run
configured by default is one nobody can account for afterwards. Each launch logs
what it resolved to.

```
Scenario knobs from preset 'knobs_default'
```

**Knobs can depend on each other.** A scenario's knobs model may carry cross-field
validators that reject an override which looks fine on its own. Veyru's
`postmortem_after_swap=true` requires `postmortem_enabled=true`, so a sweep that
disables the postmortem must pass both. Validation happens before the run claims a
directory, so a rejected config leaves no run behind and the error lands in that
launch's stdout log. When overriding one knob, override every knob the scenario
validates against it.

### Per-agent models

`--model` and `--provider` are the default an agent runs under, not the whole
answer. `model_overrides` in the config replaces the pair for the agents it names,
keyed by `agent_id`.

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
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_default \
  agents.field_observer.model=claude-opus-4-7 \
  agents.stabilization_engineer.model=gpt-5.4 \
  agents.stabilization_engineer.provider=openai
```

| | |
|---|---|
| An override must name a `model` | `provider` is optional and falls back to `--provider`, so `field_observer` above stays on Anthropic. Moving an agent to another provider takes both lines |
| The flags stay required even when every agent is overridden | Nothing runs under them, but `--provider` is still the fallback for an override that named only a model. Pick a pair you would have been happy to run |
| The launch check reads the resolved pairs | A run whose every agent is on `openai` needs no credential for the `--provider` on the command line. It needs a key for every provider some agent resolved to, plus the scenario's judge, which is its own knob (`judge_provider`) |

### Self-hosted and local models

`--provider self-hosted` points pydantic-ai at any OpenAI-compatible
chat-completions endpoint. `SELF_HOSTED_BASE_URLS` is a JSON map from model name to
`/v1` URL, so several self-hosted models coexist; `SELF_HOSTED_API_KEY` is the
bearer token shared across them.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model meta-llama/Llama-3.3-70B-Instruct --provider self-hosted \
  --runs-dir ./runs \
  --config knobs_default
```

Reference deployments live in [modal/](../modal/README.md) (Llama 3.3 70B and
Qwen3-32B on vLLM, both with tool calling). For Ollama, MLX and other local
backends, see [Local inference](local-inference-vllm-mlx.md). Pricing is keyed by
literal model name in
[token_pricing.py](../src/glossogen/token_pricing.py); add an entry there for a
model it does not know.

**Watch the context budget.** Self-hosted models are served at a small fixed
context, and `input + agent_max_tokens` must stay under it or the server rejects the
call and the run stalls. The per-cycle output cap is the `agent_max_tokens` knob
(default `16384`), not `LLM_MAX_TOKENS`. For swap and resume runs, where a
reconstructed history keeps growing, set `agent_max_tokens: 2048` in the config.

## Continuing a run

`--resume` points `run` at an existing run directory and carries on in it, keeping
the channel messages, the scenario state and each agent's history. The clock opens
at the last round the log recorded and runs to the `round_count` of the config you
pass.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --resume ./runs/<scenario>/<timestamp> \
  --config <config> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

Two uses: a run that stopped before it was done, which finishes its remaining
rounds under the configuration it was launched with; and a run that should go
further than it was configured to, which takes a raised `round_count` and extends
the same directory and the same JSONL.

Nothing compares the config you pass against what the run recorded. Round count is
the useful thing to change. Change a knob that shaped what the agents have already
seen and you get one log produced under two configurations, which nobody can
attribute afterwards.

`--runs-dir` is still required here and ignored, since `--resume` names the
directory. `--config` is the resumed run's configuration rather than a copy of the
original.

**It opens the last round the log recorded, not the one after it.** For a run that
died mid-round, that is what you want. For a run that had already ended, the final
round is played again, so the extension starts by repeating a round that already
has a verdict. To continue from a boundary instead, into a new run directory that
leaves the original untouched, use
[`resume-at-round`](agent-swaps.md#resume-at-a-round-no-replacement). To replay a
finished run with a different agent in one seat, see
[Agent swaps and resume](agent-swaps.md).

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

**Before any sweep, do one run first and read its cost**, then multiply by the
number of runs you intend. Nothing in the platform caps spend. Billing alerts and
per-key limits with your provider are the only ceiling that holds.

## Next

- [Evaluation](evaluation.md) — scoring a finished run
- [Agent swaps and resume](agent-swaps.md) — replaying a run from a chosen round
- [Scenarios](scenarios.md) — what ships in the box
- [Creating a scenario](creating-a-scenario.md) — writing your own
