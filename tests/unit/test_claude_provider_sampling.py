"""How the Claude provider forwards sampling to the anthropic SDK.

The SDK's typed ``create()`` surface dropped ``temperature`` in 1.0 while the
Messages API kept it, so the provider sends it through ``extra_body``. The
scenario judges pin ``temperature=0.0`` through this path, and a mismatch with
the installed SDK's signature fails every judged action at run time, so the
captured kwargs are also bound against the real signature here.
"""

import inspect
from typing import Any

import anthropic
import pytest
from anthropic.resources.messages import AsyncMessages
from anthropic.types import Message, ToolUseBlock, Usage
from pydantic import BaseModel

import glossogen.llm.claude_provider as claude_provider_module
from glossogen.llm.claude_provider import ClaudeProvider
from glossogen.llm.provider import LLMMessage, SamplingParams


class _Verdict(BaseModel):
    match: bool


def _tool_response() -> Message:
    """A minimal Messages response carrying one _Verdict tool call."""
    return Message(
        id="msg_test",
        content=[
            ToolUseBlock(
                id="toolu_test",
                input={"match": True},
                name="_Verdict",
                type="tool_use",
            )
        ],
        model="claude-haiku-4-5-20251001",
        role="assistant",
        stop_reason="tool_use",
        type="message",
        usage=Usage(input_tokens=1, output_tokens=1),
    )


async def test_sampling_travels_in_extra_body_and_binds_to_the_sdk_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The judge path's kwargs must be a call the installed SDK accepts."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured: dict[str, Any] = {}

    async def capture(
        client: anthropic.AsyncAnthropic,
        kwargs: dict[str, Any],
    ) -> Message:
        _ = client
        captured.update(kwargs)
        return _tool_response()

    monkeypatch.setattr(claude_provider_module, "_create_with_retry", capture)
    provider = ClaudeProvider(model="claude-haiku-4-5-20251001")

    verdict = await provider.generate_structured(
        system_prompt="Judge the match.",
        messages=[LLMMessage(role="user", content="a vs a")],
        output_schema=_Verdict,
        sampling=SamplingParams(temperature=0.0),
    )

    assert verdict.match is True
    assert "temperature" not in captured
    assert captured["extra_body"] == {"temperature": 0.0}
    # The exact kwargs the provider builds must bind against the installed
    # SDK's real signature, so the next SDK bump that drops a parameter we
    # pass fails here instead of inside every scenario judge.
    inspect.signature(AsyncMessages.create).bind(object(), **captured)


async def test_no_sampling_sends_no_body_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without sampling the model's own defaults apply, with nothing smuggled."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured: dict[str, Any] = {}

    async def capture(
        client: anthropic.AsyncAnthropic,
        kwargs: dict[str, Any],
    ) -> Message:
        _ = client
        captured.update(kwargs)
        return _tool_response()

    monkeypatch.setattr(claude_provider_module, "_create_with_retry", capture)
    provider = ClaudeProvider(model="claude-haiku-4-5-20251001")

    await provider.generate_structured(
        system_prompt="Judge the match.",
        messages=[LLMMessage(role="user", content="a vs a")],
        output_schema=_Verdict,
        sampling=None,
    )

    assert "temperature" not in captured
    assert "extra_body" not in captured
    inspect.signature(AsyncMessages.create).bind(object(), **captured)
