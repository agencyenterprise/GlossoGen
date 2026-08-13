"""A pydantic-ai model whose turns are written by the test.

Agents normally decide what to do by calling a provider. Here the decision is a
list: turn N of the script is what the agent does on its Nth cycle. Runs become
deterministic and free, so a test can assert what an agent did instead of hoping
an LLM chose it.

Built on pydantic-ai's ``FunctionModel``, which slots into the same
``build_pydantic_ai_model`` seam the real models use. Everything below the model
stays real: tools, the MCP toolset, the runtime, the event log.
"""

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, DeltaToolCalls, FunctionModel


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

    A silent fallback would let a test pass while the agent looped somewhere the
    script never described.
    """


def build_scripted_model(
    *,
    turns: Sequence[ScriptedTurn],
    when_exhausted: Sequence[ScriptedTurn] | None,
) -> FunctionModel:
    """Return a model that plays ``turns`` in order, one per model call.

    A turn is one model call, not one round. The runner wakes an agent, lets it
    act until it answers with text, then parks it until the next notification. A
    script covering a whole simulation needs turns for every one of those wakes,
    not just the first.

    ``when_exhausted`` decides what happens once the script runs out. ``None``
    raises, which is what a component test wants: an agent looping past its
    script is a bug and a silent fallback would hide it. A simulation instead
    passes the cycle an idle agent repeats, usually a poll and a reply, so the
    run can reach its own end instead of dying mid-round.

    Both a plain and a streaming implementation are supplied. The agent runner
    streams, so the streaming one is what actually runs; the plain one keeps the
    fake usable from a direct ``agent.run()``.
    """
    remaining = list(turns)
    idle_cycle = list(when_exhausted) if when_exhausted is not None else []

    def take_turn() -> ScriptedTurn:
        if not remaining:
            if not idle_cycle:
                raise ScriptExhausted(
                    f"agent asked for turn {len(turns) + 1} but the script has {len(turns)}"
                )
            remaining.extend(idle_cycle)
        return remaining.pop(0)

    def next_turn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        _ = messages
        _ = info
        turn = take_turn()
        if isinstance(turn, SayTurn):
            return ModelResponse(parts=[TextPart(content=turn.text)])
        return ModelResponse(parts=[ToolCallPart(tool_name=turn.tool_name, args=dict(turn.args))])

    async def stream_turn(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | DeltaToolCalls]:
        _ = messages
        _ = info
        turn = take_turn()
        if isinstance(turn, SayTurn):
            yield turn.text
            return
        # One delta carrying the whole call. The runner only cares that the
        # call arrives, not that it was split across chunks.
        deltas: DeltaToolCalls = {
            0: DeltaToolCall(name=turn.tool_name, json_args=json.dumps(dict(turn.args)))
        }
        yield deltas

    return FunctionModel(next_turn, stream_function=stream_turn)
