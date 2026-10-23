"""Qwen3.8-27B (dense) on Modal via vLLM's OpenAI-compatible HTTP API with tool calling.

Flags follow the vLLM recipe for Qwen3.8-27B: the ``qwen3`` reasoning parser keeps the
``<think>`` block out of the message content, ``qwen3_coder`` parses tool calls, and the
checkpoint's MTP head drafts tokens for speculative decoding.

Qwen3.8 keeps every earlier turn's reasoning in its prompt by default ("preserved
thinking"). The server sets ``preserve_thinking`` to false for every request, so the chat
template keeps only the reasoning after the last user message. The context is the model's
native 262,144 tokens.
"""

import modal

MODEL_NAME = "Qwen/Qwen3.8-27B"
N_GPU = 2
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

app = modal.App("qwen-3-8-27b")


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
        "262144",
        "--gpu-memory-utilization",
        "0.92",
        "--reasoning-parser",
        "qwen3",
        "--default-chat-template-kwargs",
        "'{\"preserve_thinking\":false}'",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "qwen3_coder",
        "--speculative-config",
        '\'{"method":"mtp","num_speculative_tokens":3}\'',
        "--uvicorn-log-level",
        "info",
    ]
    subprocess.Popen(" ".join(cmd), shell=True)
