"""Modal app for GRPO on Qwen3.8-27B: the LoRA trainer, and the vLLM server for its adapters.

The ``GRPO_APP_NAME`` environment variable names the app, and it has to be set when you deploy.
The app's volume has the same name, and its control Dict is named ``<GRPO_APP_NAME>-adapters``.
Two deployments under two names share the Hugging Face cache volume and the two secrets, and no
other volume or Dict.

``Trainer`` keeps the model, its LoRA adapter and its optimizer in GPU memory until 20 minutes
after its last call. When a step's games take longer than that, the next call starts a new
container.
``initialize(partner)`` saves step 0, an adapter whose B matrices are 0, which leaves the base
model's outputs unchanged. It also saves the run's settings, with its frozen partner, to
``runs/<run>/settings.json``.
``train_step(step, sequences)`` takes one GRPO step from adapter ``step - 1`` and saves adapter
``step`` on the volume at ``runs/<run>/adapters/step_<step>/``. A new container resumes from the
volume.

``serve`` runs vLLM with LoRA enabled. Its loader thread watches the control Dict. When the key
``request`` holds a new id, it reloads the volume and asks vLLM to load the adapter at the
request's path under the request's name. It then unloads the adapter that it loaded before, and
writes the outcome under ``result``. The adapter is then playable as a model of that name. The
server also serves the base model, without an adapter, under BASE_MODEL.

Deploy from the repository root:

    GRPO_APP_NAME=<app name> uv run --no-sync modal deploy modal/grpo/grpo_app.py
"""

import logging
import os
from pathlib import Path

from grpo_records import BASE_MODEL, GrpoSettings, StepMetrics, TrainingSequence

import modal

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
APP_NAME = os.environ["GRPO_APP_NAME"]
CONTROL_DICT = f"{APP_NAME}-adapters"
VOLUME_ROOT = Path("/grpo")
HF_CACHE = Path("/root/.cache/huggingface")
VLLM_PORT = 8000
SERVE_GPUS = 1
MINUTES = 60
HOURS = 60 * MINUTES
SETTINGS = GrpoSettings(
    lora_rank=32,
    lora_alpha=64,
    learning_rate=1e-4,
    kl_beta=0.02,
    max_grad_norm=1.0,
    logit_slice=4096,
    ratio_cap=5.0,
)

train_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "torch==2.15.0",
        "transformers==5.22.1",
        "peft==0.21.2",
        "flash-linear-attention==0.6.0",
        "accelerate==1.15.0",
        "safetensors==0.8.0",
    )
    .env({"GRPO_APP_NAME": APP_NAME})
    .add_local_file(local_path=str(HERE / "grpo_records.py"), remote_path="/root/grpo_records.py")
    .add_local_file(local_path=str(HERE / "grpo_training.py"), remote_path="/root/grpo_training.py")
)
vllm_image = (
    modal.Image.from_registry("nvidia/cuda:13.0.2-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install("vllm==0.31.0")
    .env({"GRPO_APP_NAME": APP_NAME})
    .add_local_file(local_path=str(HERE / "grpo_records.py"), remote_path="/root/grpo_records.py")
)

grpo_volume = modal.Volume.from_name(APP_NAME, create_if_missing=True)
hf_cache_volume = modal.Volume.from_name("huggingface-cache", create_if_missing=True)
control = modal.Dict.from_name(CONTROL_DICT, create_if_missing=True)

app = modal.App(APP_NAME)


def adapter_dir(*, run_name: str, step: int) -> Path:
    """Where adapter ``step`` of ``run_name`` lives on the volume."""
    return VOLUME_ROOT / "runs" / run_name / "adapters" / f"step_{step}"


@app.cls(
    image=train_image,
    gpu=["B200", "H200"],
    volumes={str(VOLUME_ROOT): grpo_volume, str(HF_CACHE): hf_cache_volume},
    secrets=[modal.Secret.from_name("huggingface-glossogen")],
    timeout=2 * HOURS,
    scaledown_window=20 * MINUTES,
    max_containers=1,
)
class Trainer:
    """One training run's model, adapter and optimizer, in GPU memory while the container runs."""

    run_name: str = modal.parameter()

    @modal.enter()
    def load(self) -> None:
        """Load the base model in bf16 and wrap it in a fresh adapter."""
        import torch
        from grpo_training import new_optimizer, with_lora
        from huggingface_hub import snapshot_download
        from transformers import Qwen3_5ForConditionalGeneration

        self.device = torch.device("cuda")
        base = Qwen3_5ForConditionalGeneration.from_pretrained(
            snapshot_download(repo_id=BASE_MODEL),
            dtype=torch.bfloat16,
            device_map="cuda",
            attn_implementation="sdpa",
        )
        self.model = with_lora(model=base, settings=SETTINGS)
        self.optimizer = new_optimizer(model=self.model, settings=SETTINGS)
        self.loaded_step = -1

    @modal.method()
    def initialize(self, partner: str) -> str:
        """Save step 0, the untrained adapter, and the run's settings; refuse a run that exists.

        ``partner`` is the JSON of the run's frozen partner, or ``null`` when every seat trains.
        """
        import json

        from grpo_training import save_state

        run_dir = VOLUME_ROOT / "runs" / self.run_name
        if run_dir.exists():
            raise ValueError(f"run {self.run_name} already exists on the volume")
        target = adapter_dir(run_name=self.run_name, step=0)
        save_state(model=self.model, optimizer=self.optimizer, directory=target, metrics=None)
        run_settings = {**SETTINGS._asdict(), "partner": json.loads(partner)}
        (run_dir / "settings.json").write_text(json.dumps(run_settings, indent=1) + "\n")
        grpo_volume.commit()
        self.loaded_step = 0
        return str(target)

    @modal.method()
    def train_step(self, step: int, sequences: list[TrainingSequence]) -> StepMetrics:
        """One GRPO step from adapter ``step - 1`` on the batch; save it as adapter ``step``."""
        from grpo_training import load_state, save_state, train_step

        target = adapter_dir(run_name=self.run_name, step=step)
        if target.exists():
            raise ValueError(f"adapter step {step} of {self.run_name} already exists")
        if self.loaded_step != step - 1:
            grpo_volume.reload()
            load_state(
                model=self.model,
                optimizer=self.optimizer,
                directory=adapter_dir(run_name=self.run_name, step=step - 1),
            )
            print(f"resumed from step {step - 1}", flush=True)
        metrics = train_step(
            model=self.model,
            optimizer=self.optimizer,
            sequences=sequences,
            device=self.device,
            settings=SETTINGS,
        )
        save_state(model=self.model, optimizer=self.optimizer, directory=target, metrics=metrics)
        grpo_volume.commit()
        self.loaded_step = step
        print(f"step {step}: {metrics._asdict()}", flush=True)
        return metrics


def post_to_vllm(*, path: str, body: dict[str, str], api_key: str) -> tuple[int, str]:
    """POST ``body`` to the local vLLM server; return the HTTP status and the response text."""
    import json
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url=f"http://127.0.0.1:{VLLM_PORT}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        logger.exception("vLLM refused %s", path)
        return error.code, error.read().decode()
    except OSError as error:
        # urllib's URLError is an OSError, so this also catches a refused connection.
        logger.exception("vLLM did not answer %s", path)
        return 0, repr(error)


def vllm_ready(*, api_key: str) -> bool:
    """Whether the local vLLM server answers its model list."""
    import urllib.request

    request = urllib.request.Request(
        url=f"http://127.0.0.1:{VLLM_PORT}/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status == 200
    except OSError:
        logger.exception("vLLM is not ready yet")
        return False


def load_adapter_requests(*, api_key: str) -> None:
    """Load each adapter that the control Dict asks for into the local vLLM server.

    Runs in a thread beside vLLM.
    """
    import time

    while not vllm_ready(api_key=api_key):
        time.sleep(10)
    print("adapter loader: vLLM is up", flush=True)
    handled = None
    loaded = None
    while True:
        time.sleep(5)
        try:
            request = control.get("request")
        except Exception:
            # A Dict read can fail for a moment. This thread reads the Dict again 5 seconds later.
            logger.exception("adapter loader: reading the control Dict failed")
            continue
        if request is None or request["id"] == handled:
            continue
        grpo_volume.reload()
        status, body = post_to_vllm(
            path="/v1/load_lora_adapter",
            body={"lora_name": request["name"], "lora_path": request["path"]},
            api_key=api_key,
        )
        unloaded = None
        if status == 200 and loaded is not None and loaded != request["name"]:
            unloaded = post_to_vllm(
                path="/v1/unload_lora_adapter", body={"lora_name": loaded}, api_key=api_key
            )[0]
        if status == 200:
            loaded = request["name"]
        control["result"] = {
            "id": request["id"],
            "status": status,
            "body": body[:2000],
            "unloaded_status": unloaded,
        }
        print(f"adapter loader: {request['name']} -> {status} {body[:300]}", flush=True)
        handled = request["id"]


def gpu_memory_mib() -> int:
    """The total memory of the container's first GPU, in MiB."""
    import subprocess

    query = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(query.stdout.split()[0])


@app.function(
    image=vllm_image,
    # H200 or H100 only. With LoRA on, vLLM 0.31 failed in its flash-attention kernel while
    # capturing CUDA graphs on a B200. The H200 containers worked.
    gpu=[f"{gpu_type}:{SERVE_GPUS}" for gpu_type in ("H200", "H100")],
    secrets=[
        modal.Secret.from_name("huggingface-glossogen"),
        modal.Secret.from_name("vllm-api-key"),
    ],
    volumes={str(VOLUME_ROOT): grpo_volume, str(HF_CACHE): hf_cache_volume},
    min_containers=1,
    max_containers=1,
    scaledown_window=15 * MINUTES,
    timeout=24 * HOURS,
)
@modal.concurrent(max_inputs=64)
@modal.web_server(port=VLLM_PORT, startup_timeout=30 * MINUTES)
def serve() -> None:
    """Launch vLLM with LoRA enabled, and the thread that loads adapters on request."""
    import subprocess
    import threading

    environment = dict(os.environ, VLLM_ALLOW_RUNTIME_LORA_UPDATING="True")
    total_mib = gpu_memory_mib()
    # On an 80 GB H100, vLLM's start-up profiling ran out of memory while capturing CUDA graphs,
    # with --gpu-memory-utilization at 0.90 and at 0.85. The profile covers the
    # vision encoder and an 8,192-token batch, so on a GPU under 100 GB the server takes no images
    # and smaller batches.
    memory_utilization = "0.90"
    small_gpu_args: list[str] = []
    if total_mib < 100_000:
        memory_utilization = "0.85"
        small_gpu_args = [
            "--limit-mm-per-prompt",
            '{"image":0,"video":0}',
            "--max-num-batched-tokens",
            "4096",
            "--max-num-seqs",
            "64",
        ]
    print(
        f"GPU memory {total_mib} MiB, gpu-memory-utilization {memory_utilization}, "
        f"extra {small_gpu_args}",
        flush=True,
    )
    command = [
        "vllm",
        "serve",
        BASE_MODEL,
        "--host",
        "0.0.0.0",
        "--port",
        str(VLLM_PORT),
        "--api-key",
        os.environ["VLLM_API_KEY"],
        "--tensor-parallel-size",
        str(SERVE_GPUS),
        "--max-model-len",
        "65536",
        "--gpu-memory-utilization",
        memory_utilization,
        "--reasoning-parser",
        "qwen3",
        "--default-chat-template-kwargs",
        '{"preserve_thinking":false}',
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "qwen3_coder",
        "--enable-lora",
        "--max-lora-rank",
        str(SETTINGS.lora_rank),
        "--max-loras",
        "2",
        "--max-cpu-loras",
        "4",
        "--uvicorn-log-level",
        "info",
        *small_gpu_args,
    ]
    subprocess.Popen(command, env=environment)
    threading.Thread(
        target=load_adapter_requests,
        kwargs={"api_key": os.environ["VLLM_API_KEY"]},
        daemon=True,
    ).start()
