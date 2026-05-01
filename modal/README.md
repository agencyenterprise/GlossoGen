# `modal/` — Self-Hosted LLM Endpoint on Modal

This folder packages a self-hosted, OpenAI-compatible LLM endpoint that the schmidt simulation runner consumes through the `--provider self-hosted` path.

The current deployment serves **`meta-llama/Llama-3.3-70B-Instruct`** at bf16 on `H100:2` via [vLLM](https://docs.vllm.ai/), with native tool calling enabled (`--enable-auto-tool-choice --tool-call-parser llama3_json`). Modal is one possible host for this pattern — the same `serve_llama.py` skeleton works on RunPod, fly.io GPU, or any environment that runs vLLM behind an HTTP server.

## Available deployments

Three Modal apps are defined here, each serving a different model. They run in parallel under separate URLs sharing the same `vllm-api-key` and `huggingface-schmidt` secrets and the same `huggingface-cache` / `vllm-cache` Modal Volumes.

| Modal app | Model | GPU | Tool/reasoning parsers | URL |
| --- | --- | --- | --- | --- |
| `llama-3-3-70b-instruct` | `meta-llama/Llama-3.3-70B-Instruct` (dense, gated) | `H100:2` bf16 | `llama3_json` (no reasoning parser) | `https://<workspace>--llama-3-3-70b-instruct-serve.modal.run/v1` |
| `qwen-3-next-80b-a3b-instruct` | `Qwen/Qwen3-Next-80B-A3B-Instruct` (MoE, 80B/3B-active, ungated) | `H200:2` bf16 | `hermes` + reasoning `qwen3` | `https://<workspace>--qwen-3-next-80b-a3b-instruct-serve.modal.run/v1` |
| `qwen-3-32b` | `Qwen/Qwen3-32B` (dense, ungated) | `H100:1` bf16 | `hermes` + reasoning `qwen3` | `https://<workspace>--qwen-3-32b-serve.modal.run/v1` |

Schmidt's `--provider self-hosted` reads `SELF_HOSTED_BASE_URLS` (a JSON object mapping model name → `/v1` URL) and looks up the URL for the model the run is launched with. List the entries you want available in `.env` to switch from the UI without redeploying.

The simulation runner forces `stream=False` on the OpenAI-compatible endpoint for `--provider self-hosted` to work around [vLLM issue #31871](https://github.com/vllm-project/vllm/issues/31871) — vLLM's `hermes` tool parser drops `<tool_call>` XML on the floor in streaming mode. Tool execution events still stream from pydantic-ai's `CallToolsNode`, so logging is unaffected.

## Files

| File | Purpose |
| --- | --- |
| `serve_llama.py` | Modal app for Llama 3.3 70B Instruct (vLLM, `H100:2` bf16). |
| `serve_qwen.py` | Modal app for Qwen3-Next-80B-A3B-Instruct (vLLM, `H200:2` bf16). |
| `serve_qwen_32b.py` | Modal app for Qwen3-32B dense (vLLM, `H100:1` bf16). |
| `tool_chat_template_llama3.1_json.jinja` | Llama 3.1/3.3 tool-calling chat template (baked into the Llama image only; Qwen uses its bundled `tokenizer_config.json` template). |
| `smoke_test_llama.py` | Ephemeral end-to-end test against the Llama endpoint. |
| `smoke_test_qwen.py` | Ephemeral end-to-end test against the Qwen3-Next-80B endpoint. |
| `smoke_test_qwen_32b.py` | Ephemeral end-to-end test against the Qwen3-32B endpoint. |

## Prerequisites

- A [Modal](https://modal.com/) account, `modal` CLI installed and authenticated (`modal token new`).
- A HuggingFace account with **the Llama 3.3 license accepted** at https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct, and a read token.

## One-time setup

Create the two Modal Secrets the app depends on:

```bash
# 1. HuggingFace token for downloading the gated Llama 3.3 weights.
modal secret create huggingface-schmidt HF_TOKEN=hf_xxx

# 2. The bearer token clients (including schmidt) use to authenticate.
modal secret create vllm-api-key VLLM_API_KEY=$(openssl rand -hex 32)
```

If you change the secret names, update [serve_llama.py](serve_llama.py) accordingly.

## Deploy

```bash
modal deploy modal/serve_llama.py
```

Modal prints the public URL on success, e.g.:

```
✓ Created web function serve =>
    https://<workspace>--llama-3-3-70b-instruct-serve.modal.run
```

The first deploy downloads ~140 GB of weights into the `huggingface-cache` Modal Volume — expect 2–4 minutes before the container is ready. Subsequent deploys hit the warm cache and start in ~30–90 s.

## Wire to a local client

Schmidt's `--provider self-hosted` reads two environment variables:

### `SELF_HOSTED_BASE_URLS` (required)

A **JSON object** mapping each served model name to its OpenAI-compatible `/v1` base URL. Schmidt looks the model up by exact name (the same string passed as `--model` or chosen in the frontend) and routes the request to the matching URL.

| Field | Value |
| --- | --- |
| **Key** | The model identifier as known to vLLM — the same string passed to `vllm serve <MODEL>`. For the deployments here that is the HuggingFace model ID (e.g. `meta-llama/Llama-3.3-70B-Instruct`, `Qwen/Qwen3-Next-80B-A3B-Instruct`). |
| **Value** | The fully-qualified base URL **including the `/v1` suffix**. Modal returns a hostname per app (`https://<workspace>--<app-name>-serve.modal.run`); append `/v1` to reach vLLM's OpenAI-compatible chat-completions API. |

The frontend reads this map to populate the model dropdown — to add a new self-hosted model, deploy it (any host) and add a key/value pair here. No code change needed.

### `SELF_HOSTED_API_KEY` (required)

A single bearer token shared across **every** entry in `SELF_HOSTED_BASE_URLS`. Schmidt sends it as `Authorization: Bearer $SELF_HOSTED_API_KEY` on every request. Each Modal app reads the same value from the `vllm-api-key` Modal Secret, so all deployments here naturally share one token. If you wire in a deployment with a different key, you currently need to align the two (one shared key per environment).

### Example `.env`

```bash
SELF_HOSTED_BASE_URLS={"meta-llama/Llama-3.3-70B-Instruct":"https://<workspace>--llama-3-3-70b-instruct-serve.modal.run/v1","Qwen/Qwen3-Next-80B-A3B-Instruct":"https://<workspace>--qwen-3-next-80b-a3b-instruct-serve.modal.run/v1","Qwen/Qwen3-32B":"https://<workspace>--qwen-3-32b-serve.modal.run/v1"}
SELF_HOSTED_API_KEY=<the VLLM_API_KEY value you generated above>
```

The JSON value must be on a single line — `.env` files do not support multi-line strings without escaping. If schmidt can't parse the JSON it logs a warning and treats the map as empty (no self-hosted models will appear in the frontend).

### Launch a simulation

```bash
VIRTUAL_ENV= uv run --no-sync python -m schmidt run veyru \
  --model meta-llama/Llama-3.3-70B-Instruct --provider self-hosted \
  --runs-dir ./runs \
  --config src/schmidt/scenarios/veyru/knobs_default.json \
  > ./runs/veyru_stdout.log 2>&1 &
```

If you can't recover the `VLLM_API_KEY` from Modal (the CLI does not expose secret values), generate a new one and `modal secret create vllm-api-key VLLM_API_KEY=<new> --force`, then redeploy so the container picks it up.

## Verify

```bash
modal run modal/smoke_test_llama.py
```

Runs an ephemeral function inside Modal (the API key never leaves Modal) that hits both a plain chat completion and a tool-calling chat completion. Pass = HTTP 200 plus a `tool_calls[0].function.name = "get_weather"` in the second response. The function retries on HTTP 303 with exponential backoff for up to 12 minutes while vLLM finishes loading the model.

## Stop the deployment when finished

All apps run with `min_containers=1`, so Modal keeps the GPUs warm and **bills continuously** until you stop them (rough order of magnitude: ~$8/hr for the Llama `H100:2` deploy, ~$9/hr for the Qwen3-Next `H200:2` deploy, ~$4/hr for the Qwen3-32B `H100:1` deploy). When you are done iterating, stop the apps you no longer need:

```bash
modal app stop llama-3-3-70b-instruct --yes
modal app stop qwen-3-next-80b-a3b-instruct --yes
modal app stop qwen-3-32b --yes
```

To confirm:

```bash
modal app list | grep -E 'llama-3-3|qwen-3-next|qwen-3-32b'   # status should read "stopped"
```

The `huggingface-cache` and `vllm-cache` Modal Volumes survive `app stop`, so the next `modal deploy` cold-starts in ~30–90 s instead of re-downloading 140–160 GB of weights. Stopping does not delete the Modal Secrets either — `huggingface-schmidt` and `vllm-api-key` persist in the workspace.

## Operating notes

- **Warm pool**: `min_containers=1` keeps one replica always warm. Stop the apps as shown above when you're done iterating.
- **Configuration**: GPU type, model name, `--max-model-len`, and `--gpu-memory-utilization` are all parameters in `serve_llama.py`. Llama 3.3 70B at bf16 fits 16384 ctx comfortably on H100:2 at 0.95 utilization; 24576 ctx is the practical ceiling before KV cache OOMs.
- **Redeploys**: when you change `vllm serve` flags, Modal launches the new container alongside the old one. With `min_containers=1` the swap can take several minutes — clients may see HTTP 303 (vLLM still loading) responses during the transition. To force a clean swap, run `modal app stop <app-name> --yes` before `modal deploy` so there is no live container to compete with the new one.
