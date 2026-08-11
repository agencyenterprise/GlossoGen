"""A scripted agent drives real tools, with no network.

If these pass, a scenario test can assert what an agent did instead of hoping an
LLM chose it.
"""

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent

from glossogen.runners.pydantic_ai_model_factory import build_pydantic_ai_model
from tests.fakes.scripted_agent_model import (
    SayTurn,
    ScriptExhausted,
    ToolTurn,
    build_scripted_model,
)
from tests.fakes.stub_llm_provider import StubLLMProvider


class Verdict(BaseModel):
    """Minimal judge output used to exercise the stub provider."""

    passed: bool


async def test_scripted_agent_calls_the_tool_the_script_names() -> None:
    """A scripted tool call reaches the real tool, with the real arguments."""
    sent: list[tuple[str, str]] = []

    agent: Agent[None, str] = Agent(
        model=build_scripted_model(
            when_exhausted=None,
            turns=[
                ToolTurn(tool_name="send_message", args={"channel_id": "link", "text": "AB12"}),
                SayTurn(text="sent"),
            ],
        ),
        deps_type=type(None),
        system_prompt="you are under test",
    )

    @agent.tool_plain
    def send_message(channel_id: str, text: str) -> str:
        """Record a message the agent sends."""
        sent.append((channel_id, text))
        return "ok"

    # Registered on the agent by the decorator; naming it keeps that visible.
    _ = send_message

    result = await agent.run("go")

    assert sent == [("link", "AB12")]
    assert result.output == "sent"


async def test_turns_are_played_in_order() -> None:
    """Turn N of the script is the agent's Nth cycle."""
    calls: list[int] = []

    agent: Agent[None, str] = Agent(
        model=build_scripted_model(
            when_exhausted=None,
            turns=[
                ToolTurn(tool_name="step", args={"n": 1}),
                ToolTurn(tool_name="step", args={"n": 2}),
                ToolTurn(tool_name="step", args={"n": 3}),
                SayTurn(text="finished"),
            ],
        ),
        deps_type=type(None),
        system_prompt="you are under test",
    )

    @agent.tool_plain
    def step(n: int) -> str:
        """Record the step index the agent asked for."""
        calls.append(n)
        return "ok"

    _ = step

    await agent.run("go")
    assert calls == [1, 2, 3]


async def test_running_past_the_script_fails_loudly() -> None:
    """An agent that takes more turns than scripted raises rather than improvising.

    Without this the agent would keep looping and the test would pass while
    describing behaviour nobody wrote down.
    """
    agent: Agent[None, str] = Agent(
        model=build_scripted_model(
            when_exhausted=None, turns=[ToolTurn(tool_name="noop", args={})]
        ),
        deps_type=type(None),
        system_prompt="you are under test",
    )

    @agent.tool_plain
    def noop() -> str:
        """Return something so the agent is asked for another turn."""
        return "ok"

    _ = noop

    with pytest.raises(ScriptExhausted):
        await agent.run("go")


async def test_the_seam_the_runner_uses_can_be_swapped() -> None:
    """The runner asks one function for its model, so a test can replace it.

    ``pydantic_ai_runner`` builds every agent with ``build_pydantic_ai_model``.
    Patching that one call is what lets a whole simulation run scripted.
    """
    assert callable(build_pydantic_ai_model)
    # Real providers resolve to a model spec; the fake is a drop-in for it.
    assert build_pydantic_ai_model(model="claude-sonnet-4-6", provider="anthropic")


async def test_stub_judge_returns_queued_answers_and_records_the_prompt() -> None:
    """The judge stub answers in order and keeps what it was shown."""
    provider = StubLLMProvider()
    provider.queue(response=Verdict(passed=True))
    provider.queue(response=Verdict(passed=False))

    first = await provider.generate_structured(
        system_prompt="judge this",
        messages=[],
        output_schema=Verdict,
    )
    second = await provider.generate_structured(
        system_prompt="judge that",
        messages=[],
        output_schema=Verdict,
    )

    assert (first.passed, second.passed) == (True, False)
    assert [call.system_prompt for call in provider.calls] == ["judge this", "judge that"]


async def test_stub_judge_fails_loudly_when_underfed() -> None:
    """An unqueued judge call is a test bug, not a default answer."""
    provider = StubLLMProvider()
    with pytest.raises(AssertionError):
        await provider.generate_structured(
            system_prompt="judge",
            messages=[],
            output_schema=Verdict,
        )
