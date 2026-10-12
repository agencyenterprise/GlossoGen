"""The guard every seat tool runs under on ``SessionSeatRunner``."""

from glossogen.runners.agent_tools import ToolOutcome
from glossogen.runners.session_harness.seat_session import SeatToolCall
from glossogen.runners.session_harness.seat_tools import guard_handler


async def test_a_handler_that_raises_answers_as_a_pydantic_ai_tool_would() -> None:
    async def broken(call: SeatToolCall) -> ToolOutcome:
        raise RuntimeError(f"broke on {call.arguments}")

    handler = guard_handler(tool_name="send_message", agent_id="observer", handler=broken)

    outcome = await handler(SeatToolCall(call_id=None, arguments={"text": "hi"}))

    assert outcome == ToolOutcome(content="Error executing tool send_message", is_error=True)


async def test_a_handler_that_answers_is_passed_through() -> None:
    async def fine(call: SeatToolCall) -> ToolOutcome:
        return ToolOutcome(content=f"got {call.call_id}", is_error=False)

    handler = guard_handler(tool_name="send_message", agent_id="observer", handler=fine)

    assert await handler(SeatToolCall(call_id="c1", arguments={})) == ToolOutcome(
        content="got c1", is_error=False
    )
