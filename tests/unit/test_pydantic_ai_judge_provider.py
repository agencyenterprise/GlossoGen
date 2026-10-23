"""The judges run through pydantic-ai, with the settings they were given.

Every judge in the platform, in-run and in ``evaluate``, goes through
``PydanticAIJudgeProvider``. A ``FunctionModel`` stands in for the provider, so
these tests read what the judge sent and decide what it gets back.
"""

from typing import NamedTuple

import pytest
from pydantic import BaseModel
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.huggingface import HuggingFaceModel
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from glossogen.llm.provider import LLMMessage
from glossogen.llm.pydantic_ai_judge_provider import (
    PydanticAIJudgeProvider,
    create_judge_provider,
)
from glossogen.models.agent_model_settings import JudgeModelSettings

INPUT_TOKENS = 900
CACHE_READ_TOKENS = 600
OUTPUT_TOKENS = 40


class Verdict(BaseModel):
    """Whether the action matched."""

    match: bool
    explanation: str


class SeenRequest(NamedTuple):
    """What one model request carried."""

    messages: list[ModelMessage]
    settings: ModelSettings | None
    output_tool_names: list[str]


def answering(answers: list[dict[str, object]], seen: list[SeenRequest]) -> FunctionModel:
    """A model that answers each request with the next output-tool arguments."""
    remaining = list(answers)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(
            SeenRequest(
                messages=list(messages),
                settings=info.model_settings,
                output_tool_names=[tool.name for tool in info.output_tools],
            )
        )
        return ModelResponse(
            parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=remaining.pop(0))],
            usage=RequestUsage(
                input_tokens=INPUT_TOKENS,
                cache_read_tokens=CACHE_READ_TOKENS,
                output_tokens=OUTPUT_TOKENS,
            ),
        )

    return FunctionModel(respond)


async def ask(
    provider: PydanticAIJudgeProvider,
    messages: list[LLMMessage],
) -> Verdict:
    """One structured judge call."""
    return await provider.generate_structured(
        system_prompt="You judge stabilization actions.",
        messages=messages,
        output_schema=Verdict,
    )


USER_ONLY = [LLMMessage(role="user", content="Was the action right?")]


async def test_the_answer_comes_back_as_the_schema_through_a_tool_named_after_it() -> None:
    seen: list[SeenRequest] = []
    provider = PydanticAIJudgeProvider(
        model=answering(answers=[{"match": True, "explanation": "same steps"}], seen=seen),
        model_settings=ModelSettings(max_tokens=2048),
    )

    verdict = await ask(provider=provider, messages=USER_ONLY)

    assert verdict == Verdict(match=True, explanation="same steps")
    assert seen[0].output_tool_names == ["Verdict"]


async def test_usage_is_booked_with_the_cached_input_apart() -> None:
    """Evaluation cost expects ``input_tokens`` to exclude what came from the cache."""
    seen: list[SeenRequest] = []
    provider = PydanticAIJudgeProvider(
        model=answering(
            answers=[{"match": True, "explanation": "a"}, {"match": False, "explanation": "b"}],
            seen=seen,
        ),
        model_settings=ModelSettings(),
    )

    await ask(provider=provider, messages=USER_ONLY)
    await ask(provider=provider, messages=USER_ONLY)

    usage = provider.get_accumulated_usage()
    assert usage.input_tokens == 2 * (INPUT_TOKENS - CACHE_READ_TOKENS)
    assert usage.cache_read_input_tokens == 2 * CACHE_READ_TOKENS
    assert usage.output_tokens == 2 * OUTPUT_TOKENS


async def test_every_call_is_sent_the_providers_settings() -> None:
    """Temperature travels in the judge's settings; no call adds or overrides one."""
    seen: list[SeenRequest] = []
    provider = PydanticAIJudgeProvider(
        model=answering(answers=[{"match": True, "explanation": "a"}], seen=seen),
        model_settings=ModelSettings(max_tokens=2048, temperature=0.0),
    )

    await ask(provider=provider, messages=USER_ONLY)

    assert seen[0].settings is not None
    assert seen[0].settings.get("temperature") == 0.0
    assert seen[0].settings.get("max_tokens") == 2048


async def test_an_answer_failing_the_schema_is_returned_to_the_model_with_the_error() -> None:
    seen: list[SeenRequest] = []
    provider = PydanticAIJudgeProvider(
        model=answering(
            answers=[{"match": "[1, 2]"}, {"match": False, "explanation": "fixed"}],
            seen=seen,
        ),
        model_settings=ModelSettings(),
    )

    verdict = await ask(provider=provider, messages=USER_ONLY)

    assert verdict == Verdict(match=False, explanation="fixed")
    retry_parts = [
        part
        for message in seen[1].messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]
    assert retry_parts, "the second request should carry the validation error"


async def test_earlier_turns_become_history_and_the_last_user_turn_the_prompt() -> None:
    seen: list[SeenRequest] = []
    provider = PydanticAIJudgeProvider(
        model=answering(answers=[{"match": True, "explanation": "a"}], seen=seen),
        model_settings=ModelSettings(),
    )

    await ask(
        provider=provider,
        messages=[
            LLMMessage(role="user", content="first question"),
            LLMMessage(role="assistant", content="first answer"),
            LLMMessage(role="user", content="second question"),
        ],
    )

    sent = seen[0].messages
    user_texts = [
        part.content
        for message in sent
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]
    assistant_texts = [
        part.content
        for message in sent
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, TextPart)
    ]
    assert user_texts == ["first question", "second question"]
    assert assistant_texts == ["first answer"]


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [LLMMessage(role="assistant", content="no question")],
        [LLMMessage(role="system", content="x"), LLMMessage(role="user", content="q")],
    ],
)
async def test_a_conversation_that_does_not_end_with_the_user_is_refused(
    messages: list[LLMMessage],
) -> None:
    seen: list[SeenRequest] = []
    provider = PydanticAIJudgeProvider(
        model=answering(answers=[], seen=seen), model_settings=ModelSettings()
    )

    with pytest.raises(ValueError):
        await ask(provider=provider, messages=messages)
    assert seen == []


def test_the_settings_given_win_over_the_provider_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A judge's own settings reach the model on top of the provider defaults."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    provider = create_judge_provider(
        provider_name="openai",
        model="gpt-5.4",
        inference_provider=None,
        settings=JudgeModelSettings(max_tokens=4096, thinking="low"),
    )

    assert isinstance(provider, PydanticAIJudgeProvider)
    settings = provider._model_settings  # pyright: ignore[reportPrivateUsage]
    assert settings.get("max_tokens") == 4096
    assert settings.get("thinking") == "low"


def test_an_anthropic_judge_keeps_prompt_caching(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    provider = create_judge_provider(
        provider_name="anthropic",
        model="claude-haiku-4-5-20251001",
        inference_provider=None,
        settings=JudgeModelSettings(),
    )

    assert isinstance(provider, PydanticAIJudgeProvider)
    settings = provider._model_settings  # pyright: ignore[reportPrivateUsage]
    assert settings.get("anthropic_cache_instructions") is True


def test_a_missing_key_fails_when_the_judge_is_built(monkeypatch: pytest.MonkeyPatch) -> None:
    """``DeferredLLMProvider`` relies on building being the credential check."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(Exception, match="ANTHROPIC_API_KEY"):
        create_judge_provider(
            provider_name="anthropic",
            model="claude-haiku-4-5-20251001",
            inference_provider=None,
            settings=JudgeModelSettings(),
        )


def test_a_huggingface_judge_is_routed_to_its_inference_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf-test")

    provider = create_judge_provider(
        provider_name="huggingface",
        model="Qwen/Qwen3-32B",
        inference_provider="together",
        settings=JudgeModelSettings(),
    )

    assert isinstance(provider, PydanticAIJudgeProvider)
    model = provider._model  # pyright: ignore[reportPrivateUsage]
    assert isinstance(model, HuggingFaceModel)
    assert model.model_name == "Qwen/Qwen3-32B"


def test_an_inference_provider_outside_huggingface_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    with pytest.raises(ValueError, match="HuggingFace"):
        create_judge_provider(
            provider_name="anthropic",
            model="claude-haiku-4-5-20251001",
            inference_provider="together",
            settings=JudgeModelSettings(),
        )


def test_a_provider_no_judge_runs_under_is_refused() -> None:
    with pytest.raises(ValueError, match="Judge providers"):
        create_judge_provider(
            provider_name="xai",
            model="grok-4.6",
            inference_provider=None,
            settings=JudgeModelSettings(),
        )


def test_a_judge_given_no_cap_sends_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset leaves the cap to the provider, which on Anthropic is the model's maximum."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    provider = create_judge_provider(
        provider_name="anthropic",
        model="claude-haiku-4-5-20251001",
        inference_provider=None,
        settings=JudgeModelSettings(),
    )

    assert isinstance(provider, PydanticAIJudgeProvider)
    settings = provider._model_settings  # pyright: ignore[reportPrivateUsage]
    assert "max_tokens" not in settings
