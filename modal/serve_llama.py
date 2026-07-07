"""Llama 3.3 70B Instruct on Modal via vLLM's OpenAI-compatible HTTP API with tool calling."""

import modal

MODEL_NAME = "meta-llama/Llama-3.3-70B-Instruct"
N_GPU = 2
VLLM_PORT = 8000
MINUTES = 60

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.9.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install(
        "vllm==0.19.1",
        "huggingface_hub[hf_transfer]",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .add_local_file(
        "modal/tool_chat_template_llama3.1_json.jinja",
        "/root/tool_chat_template_llama3.1_json.jinja",
    )
)

hf_cache_vol = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("vllm-cache", create_if_missing=True)

app = modal.App("llama-3-3-70b-instruct")


@app.function(
    image=vllm_image,
    gpu=f"H100:{N_GPU}",
    secrets=[
        modal.Secret.from_name("huggingface-glossogen"),
        modal.Secret.from_name("vllm-api-key"),
    ],
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
    min_containers=2,
    scaledown_window=15 * MINUTES,
    timeout=10 * MINUTES,
)
@modal.concurrent(max_inputs=32)
@modal.web_server(port=VLLM_PORT, startup_timeout=10 * MINUTES)
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
        "24576",
        "--gpu-memory-utilization",
        "0.95",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "llama3_json",
        "--chat-template",
        "/root/tool_chat_template_llama3.1_json.jinja",
        "--uvicorn-log-level",
        "info",
    ]
    subprocess.Popen(" ".join(cmd), shell=True)
