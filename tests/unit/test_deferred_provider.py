"""The judge provider is built on the first call, and not before.

Deferring construction is what lets a scenario be built without a key for
anybody's model. That only holds if the deferral is real, and if it still
delegates: a wrapper that never reaches its delegate breaks every judge at
runtime while "the scenario constructs" stays green.

Usage is the subtle one. `LLMProvider.__init__` gives every provider its own
zeroed accumulators, so a wrapper that inherits `get_accumulated_usage` reports
zero forever no matter what the real provider spent, and every judge's cost
quietly disappears from the evaluation report.
"""

from typing import NamedTuple, TypeVar

import pytest
from pydantic import BaseModel

from glossogen.llm import deferred_provider
from glossogen.llm.deferred_provider import DeferredLLMProvider
from glossogen.llm.provider import LLMMessage, LLMProvider, SamplingParams

T = TypeVar("T", bound=BaseModel)

INPUT_TOKENS = 120
OUTPUT_TOKENS = 34


class Verdict(BaseModel):
    """Stand-in for a judge's structured output."""

    accepted: bool


class SpendingProvider(LLMProvider):
    """Returns a fixed verdict and books token spend against itself."""

    def __init__(self) -> None:
        """Start with the base class's zeroed accumulators and no calls."""
        super().__init__()
        self.calls: list[tuple[str, str]] = []

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type[T],
        sampling: SamplingParams | None = None,
    ) -> T:
        """Record the prompt, book usage, and return the verdict."""
        _ = sampling
        self.calls.append((system_prompt, messages[0].content))
        self._record_usage(
            input_tokens=INPUT_TOKENS,
            output_tokens=OUTPUT_TOKENS,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        return output_schema.model_validate({"accepted": True})


class FactoryCall(NamedTuple):
    """The arguments the deferred provider replayed into ``create_provider``."""

    provider_name: str
    model: str
    inference_provider: str | None
    reasoning_effort: str | None


class Harness(NamedTuple):
    """A deferred provider, the delegate it will build, and the factory's log."""

    provider: DeferredLLMProvider
    delegate: SpendingProvider
    factory_calls: list[FactoryCall]


def build(monkeypatch: pytest.MonkeyPatch) -> Harness:
    """Return a deferred provider whose factory is recorded rather than real."""
    delegate = SpendingProvider()
    factory_calls: list[FactoryCall] = []

    def record(
        provider_name: str,
        model: str,
        inference_provider: str | None,
        reasoning_effort: str | None,
    ) -> LLMProvider:
        factory_calls.append(
            FactoryCall(
                provider_name=provider_name,
                model=model,
                inference_provider=inference_provider,
                reasoning_effort=reasoning_effort,
            )
        )
        return delegate

    monkeypatch.setattr(deferred_provider, "create_provider", record)
    provider = DeferredLLMProvider(
        provider_name="anthropic",
        model="claude-haiku-4-5-20251001",
        inference_provider=None,
        reasoning_effort=None,
    )
    return Harness(provider=provider, delegate=delegate, factory_calls=factory_calls)


async def judge(provider: DeferredLLMProvider) -> Verdict:
    """Run one structured call through the deferred provider."""
    return await provider.generate_structured(
        system_prompt="judge this",
        messages=[LLMMessage(role="user", content="the action")],
        output_schema=Verdict,
    )


async def test_constructing_it_builds_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """This is the whole reason the class exists, so assert it directly."""
    harness = build(monkeypatch=monkeypatch)

    assert harness.factory_calls == []


async def test_the_first_call_builds_the_delegate_and_passes_the_prompt_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wrapper that never reaches its delegate fails only at runtime."""
    harness = build(monkeypatch=monkeypatch)

    result = await judge(provider=harness.provider)

    assert result == Verdict(accepted=True)
    assert harness.delegate.calls == [("judge this", "the action")]


async def test_the_factory_replays_the_arguments_it_was_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Holding arguments and replaying them later is where they get lost."""
    harness = build(monkeypatch=monkeypatch)

    await judge(provider=harness.provider)

    assert harness.factory_calls == [
        FactoryCall(
            provider_name="anthropic",
            model="claude-haiku-4-5-20251001",
            inference_provider=None,
            reasoning_effort=None,
        )
    ]


async def test_the_delegate_is_built_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A judge runs every round, so rebuilding per call means an SDK client per round."""
    harness = build(monkeypatch=monkeypatch)

    for _ in range(3):
        await judge(provider=harness.provider)

    assert len(harness.factory_calls) == 1
    assert len(harness.delegate.calls) == 3


async def test_reading_usage_before_any_call_reports_zero_without_building(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evaluation cost reads this on providers that were never called."""
    harness = build(monkeypatch=monkeypatch)

    usage = harness.provider.get_accumulated_usage()

    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert harness.factory_calls == [], "reading usage must not build a provider"


async def test_usage_reports_what_the_delegate_spent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper has its own zeroed accumulators that nothing ever writes to.

    Inheriting `get_accumulated_usage` would report zero for every judge, and
    the cost would vanish from the evaluation report rather than fail.
    """
    harness = build(monkeypatch=monkeypatch)

    await judge(provider=harness.provider)
    await judge(provider=harness.provider)

    usage = harness.provider.get_accumulated_usage()
    assert usage.input_tokens == 2 * INPUT_TOKENS
    assert usage.output_tokens == 2 * OUTPUT_TOKENS
    assert usage == harness.delegate.get_accumulated_usage()
