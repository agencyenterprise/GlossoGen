"""Running the service on one machine with two GPUs: vLLM samples on one, the PEFT trainer trains on
the other.

``serve`` starts vLLM as a subprocess that sees only its GPU, loads Qwen3.8-27B in bf16 on the
trainer's GPU, waits until vLLM answers, and then serves the Tinker API on ``service_port``. vLLM
reads each published adapter from the checkpoint folder on the same disk, so publishing an adapter
needs no copy. ``platoon_app.py`` runs it on Modal.
"""

import asyncio
import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import aiohttp
import torch
from aiohttp import web
from huggingface_hub import snapshot_download
from tinker_service.adapter_trainer import AdapterTrainer
from tinker_service.app import build_app
from tinker_service.checkpoints import CheckpointStore
from tinker_service.peft_model import PeftLogprobModel, PeftSettings
from tinker_service.service import ServiceSettings, TinkerService
from tinker_service.vllm_backend import VllmSampler
from transformers import Qwen3_5ForConditionalGeneration

logger = logging.getLogger(__name__)

LANGUAGE_MODEL_PREFIX = "model.language_model."
VLLM_POLL_SECONDS = 10


class GpuSettings(NamedTuple):
    """Where each part runs and how it is configured."""

    model_name: str
    checkpoint_root: Path
    service_port: int
    vllm_port: int
    vllm_gpu: str
    trainer_device: str
    max_lora_rank: int
    max_loras: int
    max_cpu_loras: int
    max_model_len: int
    published_per_model: int
    logit_slice: int
    sample_timeout_seconds: float
    vllm_api_key: str
    service_api_key: str


def vllm_command(*, settings: GpuSettings) -> list[str]:
    """The ``vllm serve`` command: the base model with runtime LoRA loading, and logprobs of what it
    samples."""
    return [
        "vllm", "serve", settings.model_name,
        "--host", "127.0.0.1", "--port", str(settings.vllm_port),
        "--api-key", settings.vllm_api_key,
        "--max-model-len", str(settings.max_model_len),
        "--gpu-memory-utilization", "0.90",
        "--enable-lora", "--max-lora-rank", str(settings.max_lora_rank),
        "--max-loras", str(settings.max_loras), "--max-cpu-loras", str(settings.max_cpu_loras),
        "--logprobs-mode", "processed_logprobs",
    ]  # fmt: skip


def start_vllm(*, settings: GpuSettings, vllm_executable_dir: Path) -> subprocess.Popen[bytes]:
    """Start vLLM on its GPU, with runtime LoRA updates allowed."""
    environment = dict(os.environ)
    environment["CUDA_VISIBLE_DEVICES"] = settings.vllm_gpu
    environment["VLLM_ALLOW_RUNTIME_LORA_UPDATING"] = "True"
    environment["PATH"] = f"{vllm_executable_dir}:{environment['PATH']}"
    return subprocess.Popen(vllm_command(settings=settings), env=environment)


async def wait_for_vllm(*, settings: GpuSettings, process: subprocess.Popen[bytes]) -> None:
    """Wait until vLLM lists its models; raise when the process exits first."""
    url = f"http://127.0.0.1:{settings.vllm_port}/v1/models"
    headers = {"Authorization": f"Bearer {settings.vllm_api_key}"}
    while process.poll() is None:
        try:
            async with aiohttp.ClientSession(headers=headers) as http:
                async with http.get(url) as reply:
                    if reply.status == 200:
                        return
        except aiohttp.ClientError:
            logger.exception("vLLM is not up yet")
        await asyncio.sleep(VLLM_POLL_SECONDS)
    raise RuntimeError(f"vLLM exited with {process.returncode} before it served")


def load_trainer(*, settings: GpuSettings) -> AdapterTrainer:
    """Qwen3.8-27B in bf16 on the trainer's GPU, ready for adapters.

    The trainer's allocator uses expandable segments. Without them, a long game's rows left 18 GB
    of the trainer's GPU reserved but unallocated, and a 3.7 GB allocation failed. The setting
    applies to this process only, so the vLLM subprocess keeps its own allocator.
    """
    torch.cuda.memory._set_allocator_settings("expandable_segments:True")
    model = Qwen3_5ForConditionalGeneration.from_pretrained(
        snapshot_download(repo_id=settings.model_name),
        dtype=torch.bfloat16,
        device_map={"": settings.trainer_device},
        attn_implementation="sdpa",
    )
    peft_settings = PeftSettings(
        module_prefix=LANGUAGE_MODEL_PREFIX, logit_slice=settings.logit_slice
    )
    return AdapterTrainer(
        model=PeftLogprobModel(model=model, settings=peft_settings), base_model=settings.model_name
    )


async def serve(
    *, settings: GpuSettings, vllm_executable_dir: Path, on_saved: Callable[[], None]
) -> None:
    """Start vLLM and the trainer, then serve the Tinker API until the process ends."""
    process = start_vllm(settings=settings, vllm_executable_dir=vllm_executable_dir)
    trainer = await asyncio.to_thread(load_trainer, settings=settings)
    await wait_for_vllm(settings=settings, process=process)
    sampler = VllmSampler(
        base_url=f"http://127.0.0.1:{settings.vllm_port}",
        api_key=settings.vllm_api_key,
        base_model=settings.model_name,
        timeout_seconds=settings.sample_timeout_seconds,
    )
    service = TinkerService(
        trainer=trainer,
        sampler=sampler,
        checkpoints=CheckpointStore(root=settings.checkpoint_root),
        settings=ServiceSettings(
            base_model=settings.model_name,
            published_per_model=settings.published_per_model,
            on_saved=on_saved,
        ),
    )
    runner = web.AppRunner(build_app(service=service, api_key=settings.service_api_key))
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=settings.service_port).start()
    logger.info("serving the Tinker API on port %d", settings.service_port)
    await asyncio.Event().wait()
