"""A sampling backend over a vLLM server's OpenAI-compatible API, with LoRA adapters loaded at
runtime.

A sample is a ``/v1/completions`` request whose prompt is the token ids, with ``return_token_ids``
so that the response carries the sampled ids, ``logprobs`` for each sampled token's logprob, and
``prompt_logprobs`` when the Tinker request asks to score the prompt. Special tokens stay in the
output, and a stop string stays in it too, so the sampled ids are exactly what the model wrote.
``publish`` and ``retire`` call ``/v1/load_lora_adapter`` and ``/v1/unload_lora_adapter``, which
need ``VLLM_ALLOW_RUNTIME_LORA_UPDATING`` set on the server. The server should run with
``--logprobs-mode processed_logprobs``, so that the logprobs are those of the distribution it
sampled from.
"""

from pathlib import Path
from typing import Any

import aiohttp
from tinker_service.records import SampledSequence, SampleResult, SamplingRequest

LENGTH = "length"
STOP = "stop"


def completion_body(*, model: str, request: SamplingRequest) -> dict[str, Any]:
    """The ``/v1/completions`` body of one sampling request."""
    body: dict[str, Any] = {
        "model": model,
        "prompt": request.prompt,
        "n": request.num_samples,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "top_k": request.top_k,
        "logprobs": 1,
        "return_token_ids": True,
        "skip_special_tokens": False,
        "include_stop_str_in_output": True,
        "stop_token_ids": request.stop_tokens,
    }
    if request.max_tokens is not None:
        body["max_tokens"] = request.max_tokens
    if request.seed is not None:
        body["seed"] = request.seed
    if request.stop_strings:
        body["stop"] = request.stop_strings
    if request.prompt_logprobs:
        body["prompt_logprobs"] = 1
    return body


def sampled_sequence(*, choice: dict[str, Any]) -> SampledSequence:
    """One choice of a completion as a sampled sequence; refuse one without a logprob per token."""
    tokens = [int(token) for token in choice["token_ids"]]
    logprobs = [float(value) for value in choice["logprobs"]["token_logprobs"]]
    if len(logprobs) != len(tokens):
        raise RuntimeError(f"vLLM returned {len(tokens)} token ids and {len(logprobs)} logprobs")
    stop_reason = STOP
    if choice["finish_reason"] == LENGTH:
        stop_reason = LENGTH
    return SampledSequence(tokens=tokens, logprobs=logprobs, stop_reason=stop_reason)


def prompt_token_logprobs(*, prompt: list[int], entries: list[Any]) -> list[float | None]:
    """Each prompt token's logprob from vLLM's ``prompt_logprobs``: one mapping of token id to
    logprob per position, None at the first position."""
    if len(entries) != len(prompt):
        raise RuntimeError(f"vLLM scored {len(entries)} prompt positions of {len(prompt)}")
    scores: list[float | None] = [None]
    for token, entry in zip(prompt[1:], entries[1:], strict=True):
        scores.append(float(entry[str(token)]["logprob"]))
    return scores


class VllmSampler:
    """Samples from the vLLM server at ``base_url`` (its root, without ``/v1``), which serves
    ``base_model``."""

    def __init__(
        self, *, base_url: str, api_key: str, base_model: str, timeout_seconds: float
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.base_model = base_model
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def post(self, *, path: str, body: dict[str, Any]) -> Any:
        """POST ``body`` to the server; raise with the server's answer unless it is 200."""
        async with aiohttp.ClientSession(timeout=self.timeout, headers=self.headers) as http:
            async with http.post(f"{self.base_url}{path}", json=body) as reply:
                text = await reply.text()
                if reply.status != 200:
                    raise RuntimeError(f"vLLM {path} answered {reply.status}: {text[:2000]}")
                if reply.content_type == "application/json":
                    return await reply.json()
                return text

    async def publish(self, *, adapter: str, directory: Path) -> None:
        """Load the adapter in ``directory`` into the server under the name ``adapter``."""
        body = {"lora_name": adapter, "lora_path": str(directory)}
        await self.post(path="/v1/load_lora_adapter", body=body)

    async def retire(self, *, adapter: str) -> None:
        """Unload the adapter named ``adapter`` from the server."""
        await self.post(path="/v1/unload_lora_adapter", body={"lora_name": adapter})

    async def sample(self, *, adapter: str | None, request: SamplingRequest) -> SampleResult:
        """Sample ``request`` from ``adapter``, or from the base model when it is None."""
        model = self.base_model
        if adapter is not None:
            model = adapter
        response = await self.post(
            path="/v1/completions", body=completion_body(model=model, request=request)
        )
        choices = sorted(response["choices"], key=lambda choice: choice["index"])
        prompt_logprobs: list[float | None] | None = None
        if request.prompt_logprobs:
            prompt_logprobs = prompt_token_logprobs(
                prompt=request.prompt, entries=choices[0]["prompt_logprobs"]
            )
        return SampleResult(
            sequences=[sampled_sequence(choice=choice) for choice in choices],
            prompt_logprobs=prompt_logprobs,
        )
