# Running simulations

A run is one simulation of one scenario. Each agent's tools run inside the run
process, the scenario briefs each agent as a round opens, and every event lands in
a JSONL log that later commands read back. A round runs until the scenario
declares it settled, every agent goes idle, or the time limit passes. The game
clock watches for whichever comes first.

Between rounds, most scenarios hold a **postmortem**: a debrief phase where the
agents see the round's outcome and talk freely about what worked, on a channel
whose messages cost no budget. It is where teams refine their conventions
between attempts. The `postmortem_enabled` knob turns the phase on or off per
run. The postmortem ends when the agents go idle or its own time limit passes,
and the clock opens the next round.

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
| `--provider` | One of the [providers](#providers); required. Also the default for every agent. The `model_overrides` and `scheduled_events` knobs take the same values. The `judge_provider` knob and `glossogen evaluate --provider` take a judge provider: `anthropic`, `huggingface` or `openai` |
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
| The launch check reads the resolved pairs | A run whose every agent is on `openai` needs no credential for the `--provider` on the command line. It needs a key for every provider some agent resolved to, plus the scenario's judge, which is its own knob (`judge_provider`) and must name a judge provider |

### Providers

An agent can run under any of these. Each reads the variables in the third
column, from the environment or the nearest `.env` at or above the directory the
command runs in, and the launch check refuses a run that uses a provider whose
variables are unset. Hosted providers are priced from the `genai-prices` catalog,
each agent cycle at the rates in effect when it ended; a model the catalog does
not list runs, but is not costed.

| `--provider` | Reaches | Variables | Weights |
|---|---|---|---|
| `anthropic` | Claude | `ANTHROPIC_API_KEY` | closed |
| `openai` | GPT | `OPENAI_API_KEY` | closed |
| `google-gla` | Gemini | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | closed |
| `xai` | Grok | `XAI_API_KEY` | closed |
| `groq` | open-weight models on Groq (Llama, Qwen, gpt-oss) | `GROQ_API_KEY` | open |
| `mistral` | Mistral | `MISTRAL_API_KEY` | not classified |
| `deepseek` | DeepSeek | `DEEPSEEK_API_KEY` | open |
| `openrouter` | models from many vendors, named `vendor/model` | `OPENROUTER_API_KEY` | not classified |
| `ollama` | a local Ollama server | `OLLAMA_BASE_URL` | open |
| `self-hosted` | any OpenAI-compatible endpoint, see below | `SELF_HOSTED_BASE_URLS`, `SELF_HOSTED_API_KEY` | open |

The weights column feeds the export's `model_class`. A provider serving both
open- and closed-weight models is not classified, so a run with an agent under it
gets an empty `model_class` cell rather than a guess.

A scenario's judge and the judge `glossogen evaluate --provider` selects run only
under `anthropic`, `huggingface` or `openai`. The launch check refuses a run whose
`judge_provider` names any other provider.

**A model you trained yourself.** Serve it behind an OpenAI-compatible endpoint
(vLLM, SGLang, TGI, LM Studio) and run it as `self-hosted`, below. A fine-tune
hosted by a provider above runs under that provider with the fine-tune's model
name (`--provider openai --model ft:gpt-4.1-mini:...`). An `openai` agent is sent
`reasoning.effort` `high` only when pydantic-ai marks its model as a reasoning
model; a fine-tune is looked up by its base model, the second field of its `ft:`
name.

The `Provider` enum, `PROVIDER_SPECS`, `JUDGE_PROVIDERS` and the hosted models
the UI's pickers offer all live in
[model_catalog.py](../src/glossogen/model_catalog.py). `SIMULATION_PROVIDERS` is
derived from `PROVIDER_SPECS`, and every provider field and `--provider` flag is
checked against these. Adding a provider that pydantic-ai and `genai-prices`
already support takes a value in the enum and a row in `PROVIDER_SPECS`, plus
the pydantic-ai extra for its SDK in `pyproject.toml` when it needs one. The row
holds its variables, its pydantic-ai prefix, whether it is billed, and its
weights.

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
[Self-hosted models](local-inference-vllm-mlx.md). Tokens under `self-hosted`
and `ollama` are priced at zero, since their GPU time is billed elsewhere.

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

## Running many simulations

A sweep launches runs from a queue and keeps a fixed number live per model.
Give each provider its own queue: providers rate-limit independently, and a
single queue mixing models stalls every slot of one provider while the spec at
its head waits for a slot on the other.

```bash
#!/bin/bash
# One queue per model, run in parallel. Each spec is "<source> <knobs>".
cd "$(git rev-parse --show-toplevel)"
LOG=/tmp/sweep.log
CAP=6

declare -a GPT_SPECS=("<source_a> <knobs.json>" "<source_b> <knobs.json>")
declare -a SONNET_SPECS=("<source_c> <knobs.json>" "<source_d> <knobs.json>")

count_running_for_model() {
  pgrep -f "Python -m glossogen run veyru --model $1" 2>/dev/null | wc -l | tr -d ' '
}

launch_one() {
  local model=$1 provider=$2 source=$3 knobs=$4
  echo "$(date) [$model] launching source=$source knobs=$knobs" >> "$LOG"
  VIRTUAL_ENV= uv run --no-sync python -m glossogen replace-agent veyru \
    --source-run-dir "runs/veyru/$source" \
    --after-round 14 --rounds-after 11 \
    --replaced-agent-id field_observer \
    --model "$model" --provider "$provider" \
    --runs-dir runs --knobs "$knobs" >> "$LOG" 2>&1
  sleep 2  # run directories are named by unix second
}

process_queue() {
  local model=$1 provider=$2; shift 2
  for spec in "$@"; do
    read -r source knobs <<< "$spec"
    while [ "$(count_running_for_model "$model")" -ge "$CAP" ]; do sleep 30; done
    launch_one "$model" "$provider" "$source" "$knobs"
  done
  echo "$(date) [$model] queue complete" >> "$LOG"
}

process_queue gpt-5.4 openai "${GPT_SPECS[@]}" &
process_queue claude-sonnet-4-6 anthropic "${SONNET_SPECS[@]}" &
wait
```

Start it detached so it outlives your terminal, then watch the log and the live
simulations:

```bash
nohup bash /tmp/sweep.sh > /tmp/sweep.stdout 2>&1 &
tail -20 /tmp/sweep.log
pgrep -af "Python -m glossogen run veyru .* --resume"
```

Each `replace-agent`, `cross-run-replace-agent` and `fork-at-round` call prepares
its run directory, spawns the simulation detached, prints `new_run_id=` and
returns. The simulation writes its own `<scenario>_stdout.log` in the new
directory. A fresh `glossogen run` does not detach, so a queue of them launches
each with `&`.

**Anchor the `pgrep` pattern on the interpreter's process name.** Homebrew's
Python on macOS runs as `Python`, capitalised, so `Python -m glossogen run`
matches simulations only. A loose pattern such as `glossogen run veyru` also
matches any shell whose command line quotes it, the counting shell included.
Keep the count in a function rather than inlined into a wrapping command for the
same reason.

**Override a knob together with the knobs its validators check against it.** A
config that fails validation exits before claiming a run directory, so a
launcher that polls for new directories loses the spec without an error. The
reason is in that launch's own output, not in the launcher's log. In veyru,
`postmortem_after_swap=true` requires `postmortem_enabled=true`, and the default
preset sets the former, so a sweep with `postmortem_enabled=false` also passes
`postmortem_after_swap=false`. When unsure, launch one spec in the foreground
before queueing the sweep.

**Recompute the queue after a launcher dies.** Simulations already launched keep
running, but nothing launches the rest. Subtract the specs that already have a
run directory from the plan and start the launcher on what remains.

## Understanding cost

A run spends real money against **your own** provider keys. An agent takes many
turns per round, and every turn is an API call carrying the whole conversation so
far, so cost grows faster than the round count alone suggests.

The knobs that drive spend, roughly in order of impact:

| Knob | Effect |
|---|---|
| `round_count` | Rounds per run, the main multiplier |
| Model choice | The largest single factor. The models the pickers offer span 25× on input tokens and 20× on output, from `gpt-5.4-nano` to the Opus tier |
| `max_round_duration_seconds` | Ceiling on how long agents keep talking before a round is cut off |
| `agent_max_tokens` | Per-turn output cap (default `16384`) |
| Number of agents | Each one is an independent conversation |
| `--probe-replicas` | Evaluation only: multiplies probe calls per agent per question |

What a run itself spent is on its last event: `simulation_ended` carries
`total_cost_usd`, priced from the
[genai-prices](https://github.com/pydantic/genai-prices) catalog at the rates in
effect when the run started (see
[token_pricing.py](../src/glossogen/token_pricing.py)). A model that catalog does
not know is not costed. The web UI reads it, and so does `grep`:

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
