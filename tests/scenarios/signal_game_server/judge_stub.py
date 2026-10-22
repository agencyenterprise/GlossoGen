"""A scripted stand-in for signal_game_server's plaintext judge.

The judge is a pydantic-ai agent, so the stub is a ``FunctionModel`` put in place of the
model ``plaintext_judge`` builds. On each judge call it makes the scripted tool calls in
order, each answered by the judge's real tools on the container, then returns the
scripted verdict as the structured output. It records the texts each call was shown.
"""

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from glossogen.model_catalog import Provider
from glossogen.scenarios.signal_game_server import plaintext_judge
from glossogen.scenarios.signal_game_server.ids import JudgeTool
from glossogen.scenarios.signal_game_server.plaintext_judge import PlaintextVerdict
from glossogen.testing.scripted_agent import ToolTurn

JUDGE_TOOL_NAMES = frozenset(tool.value for tool in JudgeTool)


class ScriptedJudge:
    """The texts shown to each judge call so far, and the script every call follows."""

    def __init__(self, verdict: PlaintextVerdict, tool_turns: list[ToolTurn]) -> None:
        self._verdict = verdict
        self._tool_turns = tool_turns
        self.calls: list[str] = []

    def model(self) -> FunctionModel:
        """The model the judge agent runs on."""
        return FunctionModel(self._next_turn)

    def _next_turn(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        requests = [message for message in messages if isinstance(message, ModelRequest)]
        if len(requests) == 1:
            self.calls.append(_prompt_text(request=requests[0]))
        answered = sum(
            isinstance(part, ToolReturnPart) and part.tool_name in JUDGE_TOOL_NAMES
            for request in requests
            for part in request.parts
        )
        if answered < len(self._tool_turns):
            turn = self._tool_turns[answered]
            return ModelResponse(
                parts=[ToolCallPart(tool_name=turn.tool_name, args=dict(turn.args))]
            )
        [output_tool] = info.output_tools
        return ModelResponse(
            parts=[ToolCallPart(tool_name=output_tool.name, args=self._verdict.model_dump())]
        )


def _prompt_text(request: ModelRequest) -> str:
    """The user prompt of the judge's first request: the numbered texts."""
    for part in request.parts:
        if isinstance(part, UserPromptPart) and isinstance(part.content, str):
            return part.content
    raise AssertionError("the judge's first request carries no text prompt")


def stub_the_plaintext_judge(
    monkeypatch: pytest.MonkeyPatch, verdict: PlaintextVerdict, tool_turns: list[ToolTurn]
) -> ScriptedJudge:
    """Make every plaintext judge in the process follow ``tool_turns`` and answer ``verdict``.

    Returns the stub so a test can assert the judge was consulted, and with what.
    """
    judge = ScriptedJudge(verdict=verdict, tool_turns=tool_turns)

    def build_stub(model: str, provider: Provider) -> FunctionModel:
        _ = model, provider
        return judge.model()

    monkeypatch.setattr(plaintext_judge, "build_pydantic_ai_model", build_stub)
    return judge
