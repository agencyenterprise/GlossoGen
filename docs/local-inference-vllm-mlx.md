# Self-hosted models

Two ways to serve a model that glossogen runs against. Deploying on Modal rents
the GPUs for models too big for a laptop, with tool calling that works; the apps
for it ship in this repository. Running locally on Apple Silicon costs nothing
per hour, and Ollama is the only local option with working tool calling today.

## Modal

[modal/](../modal/README.md) ships two vLLM apps with tool calling enabled:
Llama 3.3 70B Instruct on `H100:2` and Qwen3-32B on `H100:1`. The same skeleton
works on any host that runs vLLM behind an HTTP server.

### One-time setup

You need a [Modal](https://modal.com/) account with the CLI authenticated
(`modal token new`), and for Llama a HuggingFace token with the
[Llama 3.3 license](https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct)
accepted. Then create the two secrets the apps read:

```bash
modal secret create huggingface-glossogen HF_TOKEN=hf_xxx
modal secret create vllm-api-key VLLM_API_KEY=$(openssl rand -hex 32)
```

### Deploy

```bash
modal deploy modal/serve_llama.py   # Llama 3.3 70B on H100:2
modal deploy modal/serve_qwen.py    # Qwen3-32B on H100:1
```

Modal prints the public URL on success. The first deploy downloads the weights
(~140 GB for Llama) into a Modal Volume; later deploys hit the warm cache and
start in 30 to 90 seconds.

### Wire glossogen to it

Append `/v1` to the printed hostname and put both variables in your `.env`, the
JSON on one line:

```bash
SELF_HOSTED_BASE_URLS={"meta-llama/Llama-3.3-70B-Instruct":"https://<workspace>--llama-3-3-70b-instruct-serve.modal.run/v1","Qwen/Qwen3-32B":"https://<workspace>--qwen-3-32b-serve.modal.run/v1"}
SELF_HOSTED_API_KEY=<the VLLM_API_KEY value you generated above>
```

```bash
glossogen run veyru \
  --model meta-llama/Llama-3.3-70B-Instruct --provider self-hosted \
  --runs-dir ./runs \
  --config knobs_default
```

[Running simulations](running-simulations.md#self-hosted-and-local-models) covers
the provider mechanics, including the `agent_max_tokens: 2048` override that swap
and resume runs need on a small fixed context.

### Verify

Each smoke test runs inside Modal, so the API key never leaves it, and checks a
plain completion plus a tool call:

```bash
export MODAL_LLAMA_ENDPOINT_BASE=https://<workspace>--llama-3-3-70b-instruct-serve.modal.run
modal run modal/smoke_test_llama.py
```

### Stop when finished

**The apps keep one replica warm and bill continuously**, on the order of $8/hour
for the Llama deployment and $4/hour for Qwen:

```bash
modal app stop llama-3-3-70b-instruct --yes
modal app stop qwen-3-32b --yes
```

The volumes and secrets survive a stop, so the next deploy starts in 30 to 90
seconds instead of re-downloading the weights.
[modal/README.md](../modal/README.md) carries the operating notes: context
budgets, redeploy behaviour, and the streaming workaround the runner applies.

## On Apple Silicon

Run all simulation agents against a single locally-hosted model on your Mac.
Three serving options are compared below.

### Prerequisites

- Apple Silicon Mac (M2 or later)
- Python 3.12, the version glossogen itself requires
- uv installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)

#### RAM Requirements

| RAM   | Max Model Size (4-bit quantized) | Recommended Models (Ollama / MLX)                           |
| ----- | -------------------------------- | ----------------------------------------------------------- |
| 16 GB | ~8B parameters                   | `qwen2.5:7b` / `mlx-community/Llama-3.2-3B-Instruct-4bit`   |
| 24 GB | ~14B parameters                  | `qwen2.5:14b` / `mlx-community/Qwen2.5-14B-Instruct-4bit`   |
| 32 GB | ~30B parameters                  | `qwen2.5:32b` / `mlx-community/Qwen2.5-32B-Instruct-4bit`   |
| 64 GB | ~70B parameters                  | `qwen2.5:72b` / `mlx-community/Llama-3.3-70B-Instruct-4bit` |

### Server Comparison

| Feature             | Ollama                | vllm-metal                              | vllm-mlx                   |
| ------------------- | --------------------- | --------------------------------------- | -------------------------- |
| Install             | `brew install ollama` | Shell script                            | `uv tool install vllm-mlx` |
| Concurrent batching | No (serial)           | Yes                                     | Yes                        |
| Tool calling        | Works                 | Parser works, model output inconsistent | Parser broken              |
| Simulations         | Works                 | Not reliable                            | Does not work              |
| Evaluation          | Works                 | Works                                   | Works (with patch)         |
| Maturity            | Production            | Early (official vLLM plugin)            | Early (independent)        |

**Why Ollama works but vllm-metal/vllm-mlx don't for simulations**: Ollama uses GGUF quantization and a forgiving built-in tool call parser that handles multiple output formats. vllm-metal and vllm-mlx serve MLX-quantized weights (from mlx-community on HuggingFace) where 4-bit quantization degrades the model's ability to reliably produce `<tool_call>` formatted output. The vLLM hermes parser expects exact formatting and fails silently when the model outputs double curly braces `{{...}}` or omits the tags entirely.

### Option 1: Ollama (Recommended)

Ollama has mature tool calling support and works with glossogen simulations today. Inference is serial (agents queue up), so rounds are slower with many agents.

#### Install and Setup

```bash
# Install Ollama
brew install ollama

# Pull a model
ollama pull qwen2.5:14b

# Start Ollama (if not already running)
ollama serve
```

#### Configure glossogen

Add to your `.env` file:

```bash
OLLAMA_BASE_URL="http://localhost:11434/v1"
```

The `/v1` suffix is required, because Pydantic AI uses the OpenAI-compatible endpoint.

#### Run a Simulation

```bash
glossogen run veyru \
  --model qwen2.5:14b --provider ollama --runs-dir ./runs \
  --config knobs_default \
  > ./runs/veyru_stdout.log 2>&1 &
```

#### Limitations

- **Serial inference**: Ollama processes one request at a time. Agents wait for the others to finish.
- **Language drift**: Quantized models (especially at 4-bit) occasionally produce output in unexpected languages (e.g., Thai). Larger models or higher quantization reduce this.

### Option 2: vllm-metal (Experimental)

[vllm-metal](https://github.com/vllm-project/vllm-metal) is the official community plugin that runs vLLM on Apple Silicon using MLX as the compute backend. It inherits vLLM core's tool calling infrastructure. Concurrent batching works, but tool calling is unreliable with MLX-quantized models.

#### Install

```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
source ~/.venv-vllm-metal/bin/activate
```

#### Serve a Model

```bash
vllm serve mlx-community/Qwen2.5-14B-Instruct-4bit \
  --port 8010 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

#### Known Issues

- **Double-brace tool calls**: MLX 4-bit quantized models produce `{{"name": ...}}` instead of `{"name": ...}` in tool call output. The hermes parser fails to parse this as valid JSON and returns empty `tool_calls`. A workaround is to patch `vllm/tool_parsers/hermes_tool_parser.py` to strip double braces before JSON parsing.
- **Inconsistent tool formatting**: The quantized model sometimes outputs tool calls as plain text without `<tool_call>` tags, which the parser cannot detect.

#### Configure glossogen (Evaluation Only)

```bash
OPENAI_BASE_URL=http://localhost:8010/v1
OPENAI_API_KEY=dummy
```

### Option 3: vllm-mlx (Experimental)

[vllm-mlx](https://github.com/waybarrios/vllm-mlx) is an independent reimplementation with continuous batching and multimodal support. Tool calling does not work (as of v0.2.7).

#### Install

```bash
uv tool install vllm-mlx
```

#### Serve a Model

```bash
vllm-mlx serve mlx-community/Qwen2.5-14B-Instruct-4bit --port 8010 --continuous-batching
```

Port 8010 avoids conflicting with the glossogen FastAPI backend (port 8000).

#### Known Issues (v0.2.7)

- **`load_model_with_fallback` bug**: Missing `return` statement after successful model loading. Patch `vllm_mlx/utils/tokenizer.py` line 54 to add `return model, tokenizer` after the `load()` call.
- **Tool calling broken**: `--enable-auto-tool-choice --tool-call-parser hermes` does not populate the `tool_calls` field in the API response. The parser fails to extract tool calls from model output.
- **Qwen3 not supported**: Qwen3 model architecture is not supported by mlx_lm 0.31.1 / vllm-mlx 0.2.7.

#### Configure glossogen (Evaluation Only)

```bash
OPENAI_BASE_URL=http://localhost:8010/v1
OPENAI_API_KEY=dummy
```

#### Run Evaluation

```bash
glossogen evaluate veyru \
  --run-dir ./runs/veyru/<timestamp> \
  --metrics language_strangeness,shorthand_codes \
  --model mlx-community/Qwen2.5-14B-Instruct-4bit --provider openai
```

### Performance Notes

- Rounds take longer than cloud-hosted models because all agents share a single GPU. Expect 3-10x slower throughput depending on model size and agent count.
- Monitor memory usage with `Activity Monitor`. If the system starts swapping, switch to a smaller model.
- Increase `max_round_duration_seconds` in your scenario config if agents time out waiting for inference.

### Troubleshooting

| Problem                           | Solution                                                                                     |
| --------------------------------- | -------------------------------------------------------------------------------------------- |
| `OLLAMA_BASE_URL` not set error   | Add `OLLAMA_BASE_URL="http://localhost:11434/v1"` to `.env`                                  |
| `Connection refused` on Ollama    | Run `ollama serve` to start the Ollama daemon                                                |
| `Connection refused` on port 8010 | Verify vllm-metal/vllm-mlx is running: `curl http://localhost:8010/v1/models`                |
| Out of memory / system swap       | Use a smaller quantized model that fits in your available RAM                                |
| Agents timing out                 | Increase `max_round_duration_seconds` in the scenario config                                 |
| Model responds in wrong language  | Known issue with small quantized models. Use a larger model or 8-bit quantization            |
| `OPENAI_API_KEY not set` error    | Set `OPENAI_API_KEY=dummy` in `.env` — vllm-mlx does not validate it but the SDK requires it |
