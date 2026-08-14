# Running simulations

A run is one simulation of one scenario. Agents connect to a loopback-bound MCP
server, a game clock advances rounds and delivers scenario injections, and every
event lands in a JSONL log that later commands read back.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  > ./runs/veyru_stdout.log 2>&1 &
```

On an installed package the same command is `glossogen run veyru ...`.

Output goes to a timestamped directory the CLI creates:
`<runs-dir>/<scenario>/<unix_timestamp>/`. Its layout is described under
[Run Storage](../Architecture.md#run-storage).

| Flag | |
|---|---|
| `--model` | Model identifier, required |
| `--provider` | `anthropic`, `openai`, `google-gla`, `ollama`, `self-hosted`; required |
| `--runs-dir` | Root directory for run output, required |
| `--config` | A preset the scenario ships (`knobs_default`), or a path to a JSON file of your own. Defaults to `knobs_default` |
| `--max-agent-turns` | Ceiling on agentic turns per agent (default 200) |
| `--resume` | Path to an existing run directory to continue |
| `--group-slug` | Tenant group that owns the run (default `local`) |

Run simulations in the background and pipe output to a log. Check progress by
reading that log, or by counting `round_advanced` events in the JSONL.

## Configuration

The `run` subcommand takes a base config and trailing `key=value` overrides,
Hydra-style. Values parse as JSON, so `round_count=20` is an int, `enabled=true`
a bool, and `name=alice` stays a string.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model claude-sonnet-4-6 --provider anthropic --runs-dir ./runs \
  --config knobs_intern \
  max_round_duration_seconds=120 round_count=20
```

Each scenario ships one or more presets next to its code (`knobs_default.json`
and friends) and publishes a JSON Schema for its knobs. The
[web UI](web-ui.md) and the [MCP tools](mcp-integration.md) read both, so a
preset is discoverable without reading the source.

`--config` takes the name of one of those presets, without the `.json`. Naming
the preset rather than its path is what makes one command work from a checkout
and from an installed package alike: inside a checkout the file sits under
`src/glossogen/scenarios/<name>/`, and installed it sits somewhere in
`site-packages` that nobody should have to type. A path still wins when the
argument is one, which is how an experiment keeps its own knobs JSON outside any
package. Omit the flag and the scenario's `knobs_default` is used.

The run log records which it resolved to, so a run whose configuration was
chosen rather than stated says so:

```
Scenario knobs from preset 'knobs_default'
```

**Knobs can depend on each other.** A scenario's knobs model may carry
cross-field validators that reject an override which looks fine on its own.
Veyru's `postmortem_after_swap=true` requires `postmortem_enabled=true`, so a
sweep that disables the postmortem must pass both. Validation happens before the
run claims a directory, so a rejected config leaves no run behind and the error
lands in that launch's stdout log. When overriding one knob, override every knob
the scenario validates against it, and launch one run in the foreground first if
you are unsure.

### Per-agent models

Every agent uses `--model` / `--provider` unless overridden. Overrides live under
`model_overrides` in the config:

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
field:

```bash
agents.stabilization_engineer.model=gpt-5.4 agents.stabilization_engineer.provider=openai
```

### Self-hosted and local models

`--provider self-hosted` points pydantic-ai at any OpenAI-compatible
chat-completions endpoint. `SELF_HOSTED_BASE_URLS` is a JSON map from model name
to `/v1` URL, so several self-hosted models coexist; `SELF_HOSTED_API_KEY` is the
bearer token shared across them.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run veyru \
  --model meta-llama/Llama-3.3-70B-Instruct --provider self-hosted \
  --runs-dir ./runs
```

Reference deployments live in [modal/](../modal/README.md) (Llama 3.3 70B and
Qwen3-32B on vLLM, both with tool calling). For Ollama, MLX and other local
backends, see [Local inference](local-inference-vllm-mlx.md). Pricing is keyed by
literal model name in
[token_pricing.py](../src/glossogen/token_pricing.py); add an entry there for a
model it does not know.

**Watch the context budget.** Self-hosted models are served at a small fixed
context, and `input + agent_max_tokens` must stay under it or the server rejects
the call and the run stalls. The per-cycle output cap is the `agent_max_tokens`
knob (default `16384`), not `LLM_MAX_TOKENS`. For swap and resume runs, where a
reconstructed history keeps growing, set `agent_max_tokens: 2048` in the config.

## Resuming after a crash

If a simulation crashes or is killed, resume it with `--resume` pointing at the
existing run directory. It picks up where it stopped, keeping channel messages and
scenario state, and requires the same `--config` as the original.

```bash
VIRTUAL_ENV= uv run --no-sync python -m glossogen run <scenario> \
  --model <model> --provider <provider> --runs-dir ./runs \
  --resume ./runs/<scenario>/<timestamp> \
  --config <original-config.json> \
  > ./runs/<scenario>/<timestamp>/resume_stdout.log 2>&1 &
```

This is crash recovery. To replay a finished run from a chosen round, with or
without swapping an agent, see [Agent swaps and resume](agent-swaps.md).

## Understanding cost

Running a simulation spends real money against **your own** provider keys. An
agent takes many turns per round, and every turn is an API call carrying the full
conversation so far, so cost grows faster than round count alone suggests.

The knobs that drive spend, roughly in order of impact:

| Knob | Effect |
|---|---|
| `round_count` | Rounds per run, the main multiplier |
| Model choice | The largest single factor. A frontier model can cost 10–30× a small one for identical work |
| `max_round_duration_seconds` | Ceiling on how long agents keep talking before a round is cut off |
| `agent_max_tokens` | Per-turn output cap (default `16384`) |
| Number of agents | Each one is an independent conversation |
| `--probe-replicas` | Evaluation only: multiplies probe calls per agent per question |

Actual per-run cost is recorded in the run's evaluation report under
`evaluation_cost`, and per-model pricing lives in
[token_pricing.py](../src/glossogen/token_pricing.py).

**Before any sweep, do one run first and read its cost.** Multiply by the number
of runs you intend. This is the single easiest expensive mistake to make.

Nothing in the platform caps spend. Set billing alerts and per-key limits with
your provider. That is the only ceiling that holds.

## Next

- [Evaluation](evaluation.md) — scoring a finished run
- [Agent swaps and resume](agent-swaps.md) — replaying a run from a chosen round
- [Scenarios](scenarios.md) — what ships in the box
- [Creating a scenario](creating-a-scenario.md) — writing your own
