"""A pydantic-ai model whose every turn is written by the test.

Agents normally decide what to do by calling a provider. Here the decision is a
list: turn N of the script is what the agent does on its Nth cycle. That makes a
simulation deterministic and free to run, so a test can assert what the agent
did rather than what an LLM happened to choose.

Built on pydantic-ai's ``FunctionModel``, so it plugs into the same seam the
real models use — ``build_pydantic_ai_model`` — and everything downstream of the
model (tools, the MCP toolset, the runtime, the event log) stays real.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel


@dataclass(frozen=True)
class ToolTurn:
    """One turn in which the agent calls a tool."""

    tool_name: str
    args: dict[str, object]


@dataclass(frozen=True)
class SayTurn:
    """One turn in which the agent replies with text and stops."""

    text: str


ScriptedTurn = ToolTurn | SayTurn


class ScriptExhausted(RuntimeError):
    """Raised when an agent takes more turns than the script provides.

    Deliberately loud: a silent fallback would let a test pass while the agent
    looped somewhere the script never described.
    """


def build_scripted_model(*, turns: Sequence[ScriptedTurn]) -> FunctionModel:
    """Return a model that plays ``turns`` in order, one per agent cycle."""
    remaining = list(turns)

    def next_turn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = messages
        _ = info
        if not remaining:
            raise ScriptExhausted(
                f"agent asked for turn {len(turns) + 1} but the script has {len(turns)}"
            )
        turn = remaining.pop(0)
        if isinstance(turn, SayTurn):
            return ModelResponse(parts=[TextPart(content=turn.text)])
        return ModelResponse(parts=[ToolCallPart(tool_name=turn.tool_name, args=dict(turn.args))])

    return FunctionModel(next_turn)
