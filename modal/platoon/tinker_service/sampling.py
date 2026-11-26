"""What the service needs of a sampling backend: load and unload adapters, and sample.

``vllm_backend`` implements it over a vLLM server, and ``scripted_backend`` over a script, for CPU
tests. An adapter is named when it is published; a sample names the adapter it samples, or None for
the base model.
"""

from pathlib import Path
from typing import Protocol

from tinker_service.records import SampleResult, SamplingRequest


class SamplingBackend(Protocol):
    """A sampler of the base model and of the adapters published to it."""

    async def publish(self, *, adapter: str, directory: Path) -> None:
        """Load the adapter in ``directory`` under the name ``adapter``."""
        ...

    async def retire(self, *, adapter: str) -> None:
        """Unload the adapter named ``adapter``."""
        ...

    async def sample(self, *, adapter: str | None, request: SamplingRequest) -> SampleResult:
        """Sample ``request`` from ``adapter``, or from the base model when it is None."""
        ...
