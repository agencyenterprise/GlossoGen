"""A sampling backend for CPU tests: a script writes each completion from the decoded prompt.

The backend decodes the prompt's tokens, asks the script for the completion's text, and encodes it
followed by the stop token, as a model that ended its turn writes it. Every sampled token gets the
same logprob, and so does every prompt token when prompt logprobs are asked for. It records which
adapter each sample asked for and whether it scored a prompt, and refuses an adapter that was never
published or was retired.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from tinker_service.records import SampledSequence, SampleResult, SamplingRequest

STOP = "stop"
LENGTH = "length"


class SampleCall(NamedTuple):
    """One sample the backend answered: its adapter (None for the base model), and whether it scored
    a prompt."""

    adapter: str | None
    scoring: bool


class ScriptedSampler:
    """Completions from ``script``, tokenized with ``tokenizer``."""

    def __init__(
        self,
        *,
        tokenizer: Any,
        script: Callable[[str], str],
        stop_token: str,
        logprob: float,
        prompt_logprob: float,
    ) -> None:
        self.tokenizer = tokenizer
        self.script = script
        self.stop_id = int(tokenizer.convert_tokens_to_ids(stop_token))
        self.logprob = logprob
        self.prompt_logprob = prompt_logprob
        self.published: set[str] = set()
        self.calls: list[SampleCall] = []

    async def publish(self, *, adapter: str, directory: Path) -> None:
        """Note the adapter as published; refuse a folder that holds no files."""
        if not directory.is_dir() or not any(directory.iterdir()):
            raise ValueError(f"no adapter files in {directory}")
        self.published.add(adapter)

    async def retire(self, *, adapter: str) -> None:
        """Note the adapter as retired."""
        self.published.discard(adapter)

    async def sample(self, *, adapter: str | None, request: SamplingRequest) -> SampleResult:
        """The script's completion of the decoded prompt, ``num_samples`` times."""
        if adapter is not None and adapter not in self.published:
            raise ValueError(f"adapter {adapter!r} is not published")
        self.calls.append(SampleCall(adapter=adapter, scoring=request.prompt_logprobs))
        sequences = [self.completion(request=request) for _ in range(request.num_samples)]
        prompt_logprobs: list[float | None] | None = None
        if request.prompt_logprobs:
            prompt_logprobs = [None] + [self.prompt_logprob] * (len(request.prompt) - 1)
        return SampleResult(sequences=sequences, prompt_logprobs=prompt_logprobs)

    def completion(self, *, request: SamplingRequest) -> SampledSequence:
        """One completion, cut at ``max_tokens``."""
        text = self.script(self.tokenizer.decode(request.prompt, skip_special_tokens=False))
        tokens = [*self.tokenizer.encode(text, add_special_tokens=False), self.stop_id]
        stop_reason = STOP
        if request.max_tokens is not None and len(tokens) > request.max_tokens:
            tokens = tokens[: request.max_tokens]
            stop_reason = LENGTH
        return SampledSequence(
            tokens=tokens, logprobs=[self.logprob] * len(tokens), stop_reason=stop_reason
        )
