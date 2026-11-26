"""Modal app of the Tinker-API service that ``platoon train`` trains Qwen3.8-27B through.

One container holds two H200 GPUs. vLLM serves Qwen3.8-27B with LoRA on the second GPU, and the
service trains the adapters with PEFT on the first and answers the Tinker API at the ``tinker_api``
function's web URL (``tinker_service.gpu_runtime``). The ``PLATOON_APP_NAME`` environment variable
names the app and its volume, which holds every checkpoint under ``/platoon/checkpoints``. The
service keeps its sessions and adapters in memory, so the container stays up while the app is
deployed (``min_containers=1``); stop the app when training ends.

The app needs three Modal secrets: ``huggingface-glossogen`` (``HF_TOKEN``), ``vllm-api-key``
(``VLLM_API_KEY``, which the service uses to reach its own vLLM) and ``platoon-tinker-api-key``
(``TINKER_API_KEY``, a key that starts with ``tml-``, which the service requires of every client).
Deploy from ``modal/platoon`` with the repository's environment, which has the modal CLI:

    PLATOON_APP_NAME=platoon-$USER VIRTUAL_ENV= uv run --no-sync --project ../.. modal deploy
    platoon_app.py
"""

import os
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
APP_NAME = os.environ["PLATOON_APP_NAME"]
MODEL_NAME = "Qwen/Qwen3.8-27B"
VOLUME_ROOT = Path("/platoon")
HF_CACHE = Path("/root/.cache/huggingface")
VLLM_BIN = Path("/opt/vllm/bin")
SERVICE_PORT = 8000
VLLM_PORT = 8001
MINUTES = 60
HOURS = 60 * MINUTES

image = (
    modal.Image.from_registry("nvidia/cuda:13.0.2-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install(
        "torch==2.15.0",
        "transformers==5.22.1",
        "peft==0.21.2",
        "flash-linear-attention==0.6.0",
        "accelerate==1.15.0",
        "safetensors==0.8.0",
        "tinker==0.16.1",
        "aiohttp==3.14.5",
        "pydantic==2.14.4",
    )
    # vLLM pins its own torch and transformers, so it gets a virtualenv of its own.
    .run_commands("python -m venv /opt/vllm", "/opt/vllm/bin/pip install vllm==0.31.0")
    .env({"PLATOON_APP_NAME": APP_NAME})
    .add_local_dir(local_path=str(HERE / "tinker_service"), remote_path="/root/tinker_service")
)

checkpoint_volume = modal.Volume.from_name(APP_NAME, create_if_missing=True)
hf_cache_volume = modal.Volume.from_name("huggingface-cache", create_if_missing=True)

app = modal.App(APP_NAME)


@app.function(
    image=image,
    # H200 only: with LoRA on, vLLM 0.31 failed in its flash-attention kernel while capturing CUDA
    # graphs on a B200.
    gpu="H200:2",
    volumes={str(VOLUME_ROOT): checkpoint_volume, str(HF_CACHE): hf_cache_volume},
    secrets=[
        modal.Secret.from_name("huggingface-glossogen"),
        modal.Secret.from_name("vllm-api-key"),
        modal.Secret.from_name("platoon-tinker-api-key"),
    ],
    min_containers=1,
    max_containers=1,
    timeout=24 * HOURS,
)
@modal.concurrent(max_inputs=1000)
@modal.web_server(port=SERVICE_PORT, startup_timeout=60 * MINUTES)
def tinker_api() -> None:
    """Start vLLM, the trainer and the Tinker-API routes in a thread; the routes answer once both
    are up."""
    import asyncio
    import threading

    from tinker_service.gpu_runtime import GpuSettings, serve

    settings = GpuSettings(
        model_name=MODEL_NAME,
        checkpoint_root=VOLUME_ROOT / "checkpoints",
        service_port=SERVICE_PORT,
        vllm_port=VLLM_PORT,
        vllm_gpu="1",
        trainer_device="cuda:0",
        max_lora_rank=32,
        max_loras=4,
        max_cpu_loras=16,
        max_model_len=65536,
        published_per_model=6,
        logit_slice=4096,
        sample_timeout_seconds=900.0,
        vllm_api_key=os.environ["VLLM_API_KEY"],
        service_api_key=os.environ["TINKER_API_KEY"],
    )

    def run() -> None:
        asyncio.run(
            serve(
                settings=settings, vllm_executable_dir=VLLM_BIN, on_saved=checkpoint_volume.commit
            )
        )

    threading.Thread(target=run, daemon=True).start()
