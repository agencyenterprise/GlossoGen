"""Token counting through pydantic-ai models, with no network."""

import logging

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, UserPromptPart
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from glossogen.llm.token_counter import (
    HeuristicTokenCounter,
    ModelTokenCounter,
    create_token_counter,
)
from glossogen.model_catalog import SELF_HOSTED_BASE_URLS_VAR, Provider


class CountingModel(Model):
    """A model whose ``count_tokens`` returns a fixed count, or raises when told to."""

    def __init__(self, input_tokens: int, error: Exception | None) -> None:
        super().__init__()
        self.input_tokens = input_tokens
        self.error = error
        self.counted_texts: list[str] = []

    @property
    def model_name(self) -> str:
        return "counting-model"

    @property
    def system(self) -> str:
        return "stub"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        _ = messages
        _ = model_settings
        _ = model_request_parameters
        raise AssertionError("token counting must not make a model request")

    async def count_tokens(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> RequestUsage:
        _ = model_settings
        _ = model_request_parameters
        for message in messages:
            assert isinstance(message, ModelRequest)
            for part in message.parts:
                assert isinstance(part, UserPromptPart)
                assert isinstance(part.content, str)
                self.counted_texts.append(part.content)
        if self.error is not None:
            raise self.error
        return RequestUsage(input_tokens=self.input_tokens)


async def test_a_counting_model_returns_its_count() -> None:
    model = CountingModel(input_tokens=7, error=None)
    counter = ModelTokenCounter(model=model)

    assert await counter.count(text="three short words") == 7
    assert model.counted_texts == ["three short words"]


async def test_a_repeated_text_is_counted_once() -> None:
    model = CountingModel(input_tokens=7, error=None)
    counter = ModelTokenCounter(model=model)

    await counter.count(text="same text")
    await counter.count(text="same text")

    assert model.counted_texts == ["same text"]


async def test_a_failed_count_falls_back_to_the_word_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = CountingModel(input_tokens=7, error=RuntimeError("endpoint down"))
    counter = ModelTokenCounter(model=model)

    with caplog.at_level(logging.ERROR, logger="glossogen.llm.token_counter"):
        assert await counter.count(text="three short words") == 3

    assert any(record.exc_info is not None for record in caplog.records)


def test_a_provider_with_token_counting_gets_a_model_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    counter = create_token_counter(provider=Provider.ANTHROPIC, model="claude-haiku-4-5")

    assert isinstance(counter, ModelTokenCounter)


async def test_a_provider_without_token_counting_gets_the_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    counter = create_token_counter(provider=Provider.GROQ, model="llama-3.3-70b-versatile")

    assert isinstance(counter, HeuristicTokenCounter)
    assert await counter.count(text="three short words") == 3


def test_a_model_that_cannot_be_built_gets_the_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SELF_HOSTED_BASE_URLS_VAR, "{}")

    counter = create_token_counter(provider=Provider.SELF_HOSTED, model="unconfigured")

    assert isinstance(counter, HeuristicTokenCounter)
