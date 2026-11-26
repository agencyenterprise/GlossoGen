"""The vLLM sampling backend against a stand-in server that answers as vLLM's OpenAI-compatible API
does: the requests it sends, and how it reads the sampled ids, their logprobs and the prompt's
logprobs."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from tinker_service.records import SamplingRequest
from tinker_service.vllm_backend import VllmSampler

HOST = "127.0.0.1"
REQUESTS_KEY = web.AppKey("requests", list[tuple[str, dict[str, Any]]])
BASE_MODEL = "Qwen/Qwen3.8-27B"
FINISH_REASONS = ("stop", "length")


async def completions(request: web.Request) -> web.Response:
    """Two sampled tokens per choice, and the prompt's logprobs when asked for."""
    body = await request.json()
    request.app[REQUESTS_KEY].append((request.path, body))
    choices = []
    for index in range(body["n"]):
        choice: dict[str, Any] = {
            "index": index,
            "text": "ok",
            "token_ids": [11, 12],
            "logprobs": {"token_logprobs": [-0.5, -0.25]},
            "finish_reason": FINISH_REASONS[index % 2],
        }
        if "prompt_logprobs" in body:
            choice["prompt_logprobs"] = [None] + [
                {str(token): {"logprob": -1.0 * token, "rank": 1}} for token in body["prompt"][1:]
            ]
        choices.append(choice)
    return web.json_response({"choices": choices})


async def adapters(request: web.Request) -> web.Response:
    """Load or unload an adapter, as vLLM answers it: plain text."""
    request.app[REQUESTS_KEY].append((request.path, await request.json()))
    return web.Response(text="Success")


@asynccontextmanager
async def stand_in_vllm() -> AsyncIterator[tuple[str, list[tuple[str, dict[str, Any]]]]]:
    """Serve the stand-in on a free port; yield its root URL and the requests it receives."""
    app = web.Application()
    requests: list[tuple[str, dict[str, Any]]] = []
    app[REQUESTS_KEY] = requests
    app.router.add_post("/v1/completions", completions)
    app.router.add_post("/v1/load_lora_adapter", adapters)
    app.router.add_post("/v1/unload_lora_adapter", adapters)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=HOST, port=0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]
    try:
        yield f"http://{HOST}:{port}", requests
    finally:
        await runner.cleanup()


def sampling_request(*, prompt_logprobs: bool, num_samples: int) -> SamplingRequest:
    """A request to sample after the prompt [5, 6, 7]."""
    return SamplingRequest(
        prompt=[5, 6, 7],
        max_tokens=2,
        temperature=1.0,
        top_k=-1,
        top_p=1.0,
        seed=None,
        stop_strings=[],
        stop_tokens=[99],
        num_samples=num_samples,
        prompt_logprobs=prompt_logprobs,
    )


async def test_a_sample_sends_the_token_prompt_and_reads_ids_and_logprobs() -> None:
    async with stand_in_vllm() as (url, requests):
        sampler = VllmSampler(base_url=url, api_key="k", base_model=BASE_MODEL, timeout_seconds=30)
        result = await sampler.sample(
            adapter="model-1-sampler-2",
            request=sampling_request(prompt_logprobs=False, num_samples=2),
        )
    path, body = requests[0]
    assert path == "/v1/completions"
    assert body["model"] == "model-1-sampler-2" and body["prompt"] == [5, 6, 7]
    assert body["return_token_ids"] is True and body["skip_special_tokens"] is False
    assert body["stop_token_ids"] == [99] and "stop" not in body and "prompt_logprobs" not in body
    assert [sequence.stop_reason for sequence in result.sequences] == ["stop", "length"]
    assert result.sequences[0].tokens == [11, 12]
    assert result.sequences[0].logprobs == [-0.5, -0.25]
    assert result.prompt_logprobs is None


async def test_scoring_the_base_model_reads_each_prompt_token_s_logprob() -> None:
    async with stand_in_vllm() as (url, requests):
        sampler = VllmSampler(base_url=url, api_key="k", base_model=BASE_MODEL, timeout_seconds=30)
        result = await sampler.sample(
            adapter=None, request=sampling_request(prompt_logprobs=True, num_samples=1)
        )
    assert requests[0][1]["model"] == BASE_MODEL
    assert result.prompt_logprobs == [None, -6.0, -7.0]


async def test_publish_and_retire_load_and_unload_the_adapter(tmp_path: Path) -> None:
    async with stand_in_vllm() as (url, requests):
        sampler = VllmSampler(base_url=url, api_key="k", base_model=BASE_MODEL, timeout_seconds=30)
        await sampler.publish(adapter="model-1-final", directory=tmp_path)
        await sampler.retire(adapter="model-1-final")
    assert requests == [
        ("/v1/load_lora_adapter", {"lora_name": "model-1-final", "lora_path": str(tmp_path)}),
        ("/v1/unload_lora_adapter", {"lora_name": "model-1-final"}),
    ]


async def test_an_error_from_the_server_raises() -> None:
    async with stand_in_vllm() as (url, _):
        sampler = VllmSampler(
            base_url=f"{url}/missing", api_key="k", base_model=BASE_MODEL, timeout_seconds=30
        )
        with pytest.raises(RuntimeError, match="answered 404"):
            await sampler.retire(adapter="x")
