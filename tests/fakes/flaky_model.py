"""A scripted model whose numbered requests fail, for tests of the runner's retries and restarts.

``FlakyModelRecorder`` wraps a scripted model, records every request it receives
and raises ``ProviderUnavailable`` on the requests numbered in ``failing``.
``no_retry_pause`` stands in for tenacity's sleep, and ``BUILD_SCRIPTED_MODEL`` is
the harness's own builder, captured at import so a test that monkeypatches the
harness wraps the original builder and not an earlier wrapper.
"""

from collections.abc import AsyncIterator

from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import (
    AgentInfo,
    BuiltinToolCallsReturns,
    DeltaThinkingCalls,
    DeltaToolCalls,
    FunctionModel,
)

from glossogen.testing import simulation_harness

BUILD_SCRIPTED_MODEL = simulation_harness.build_scripted_model


async def no_retry_pause(_seconds: float) -> None:
    """Stand in for tenacity's sleep: the retry pause is wall-clock time a test does not spend."""
    return None


class ProviderUnavailable(RuntimeError):
    """The error a failing request raises."""


class FlakyModelRecorder:
    """Wraps a scripted model so the requests numbered in ``failing`` fail, and records all."""

    def __init__(self, scripted: FunctionModel, failing: frozenset[int]) -> None:
        self._scripted = scripted
        self._failing = failing
        self.requests: list[list[ModelMessage]] = []

    def model(self) -> FunctionModel:
        """Return the wrapping model."""

        async def stream(
            messages: list[ModelMessage], info: AgentInfo
        ) -> AsyncIterator[str | DeltaToolCalls | DeltaThinkingCalls | BuiltinToolCallsReturns]:
            self.requests.append(list(messages))
            if len(self.requests) in self._failing:
                raise ProviderUnavailable("provider unavailable")
            assert self._scripted.stream_function is not None
            async for chunk in self._scripted.stream_function(messages, info):
                yield chunk

        return FunctionModel(stream_function=stream)
