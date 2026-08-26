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
from collections.abc import AsyncIterator, Callable, Sequence
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


@dataclass(frozen=True)
class RoundGate:
    """Holds the turns after it until the simulation reaches ``round_number``.

    Not a turn of its own. While the gate is closed the model alternates a
    blocking ``read_notifications`` poll with a text reply, so the agent parks
    idle between wakes and the game clock can end the round under it. The turn
    after the gate plays in the same cycle as the poll that saw the round
    arrive. Only :func:`build_round_paced_model` understands gates.
    """

    round_number: int


PacedTurn = ScriptedTurn | RoundGate


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

    return _model_playing(take_turn=take_turn)


def build_round_paced_model(
    *,
    turns: Sequence[PacedTurn],
    when_exhausted: Sequence[ScriptedTurn] | None,
    current_round: Callable[[], int],
) -> FunctionModel:
    """Return a model that plays ``turns`` in order, holding at each ``RoundGate``.

    ``current_round`` is read live at every model call, so where a turn lands is
    decided by the simulation's own round counter rather than by how the machine
    scheduled the cycles. A closed gate costs one blocking ``read_notifications``
    poll, then a text reply when the wake was not the round opening, so a gated
    agent is parked idle whenever it has nothing to do.

    ``when_exhausted`` behaves as in :func:`build_scripted_model`.
    """
    remaining: list[PacedTurn] = list(turns)
    idle_cycle = list(when_exhausted) if when_exhausted is not None else []
    total = len(remaining)
    poll_pending = False

    def take_turn() -> ScriptedTurn:
        nonlocal poll_pending
        while remaining and isinstance(remaining[0], RoundGate):
            gate = remaining[0]
            if current_round() >= gate.round_number:
                remaining.pop(0)
                poll_pending = False
                continue
            if poll_pending:
                # The poll came back and the round has not advanced, so the
                # wake was something else. Reply to end the cycle, then poll
                # again on the next one.
                poll_pending = False
                return SayTurn(text=f"waiting for round {gate.round_number}")
            poll_pending = True
            return ToolTurn(tool_name="read_notifications", args={})
        if not remaining:
            if not idle_cycle:
                raise ScriptExhausted(f"agent asked for a turn beyond the script's {total}")
            remaining.extend(idle_cycle)
        turn = remaining.pop(0)
        if isinstance(turn, RoundGate):
            raise AssertionError("the gate loop above consumes every RoundGate")
        return turn

    return _model_playing(take_turn=take_turn)


def _model_playing(take_turn: Callable[[], ScriptedTurn]) -> FunctionModel:
    """Wrap a turn source in the plain and streaming pydantic-ai model functions."""

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
