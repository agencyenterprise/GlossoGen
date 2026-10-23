"""gpt-oss-120b (MoE) on Modal via vLLM's OpenAI-compatible HTTP API with tool calling.

The checkpoint ships in MXFP4, which fits one H100. ``--tool-call-parser openai`` parses
the harmony-format tool calls the vLLM recipe for gpt-oss documents.
"""

import modal

MODEL_NAME = "openai/gpt-oss-120b"
N_GPU = 1
# In order of preference: Modal starts the container on the first type with capacity.
GPU_TYPES = ("H100", "H200", "A100-80GB")
VLLM_PORT = 8000
MINUTES = 60

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:13.0.2-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install("vllm==0.31.0")
)

hf_cache_vol = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache", create_if_missing=True)

app = modal.App("gpt-oss-120b")


@app.function(
    image=vllm_image,
    gpu=[f"{gpu_type}:{N_GPU}" for gpu_type in GPU_TYPES],
    secrets=[
        modal.Secret.from_name("huggingface-glossogen"),
        modal.Secret.from_name("vllm-api-key"),
    ],
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
    min_containers=1,
    max_containers=1,
    scaledown_window=15 * MINUTES,
    timeout=30 * MINUTES,
)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=VLLM_PORT, startup_timeout=30 * MINUTES)
def serve() -> None:
    """Launch vLLM's OpenAI-compatible server as a subprocess; Modal proxies inbound HTTPS to it."""
    import os
    import subprocess

    cmd = [
        "vllm",
        "serve",
        MODEL_NAME,
        "--host",
        "0.0.0.0",
        "--port",
        str(VLLM_PORT),
        "--api-key",
        os.environ["VLLM_API_KEY"],
        "--tensor-parallel-size",
        str(N_GPU),
        "--max-model-len",
        "131072",
        "--gpu-memory-utilization",
        "0.95",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "openai",
        "--uvicorn-log-level",
        "info",
    ]
    subprocess.Popen(" ".join(cmd), shell=True)
