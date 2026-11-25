"""A seat on another model than its source agent starts without the source's thinking.

A provider takes back only the thinking that its own model wrote. Thinking parts
from another model reach the seat as empty reasoning items, so the transfer
leaves them out and keeps the text and tool calls around them.
"""

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    UserPromptPart,
)

from glossogen.run_replay.transferred_history import without_thinking


def test_thinking_parts_go_and_the_rest_of_each_response_stays() -> None:
    """Text and tool calls keep their order; only thinking parts are removed."""
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="start")]),
        ModelResponse(
            parts=[
                ThinkingPart(content="", signature="sig", provider_name="anthropic"),
                TextPart(content="I will move."),
                ToolCallPart(tool_name="move", args={"square": "B3"}, tool_call_id="c1"),
            ]
        ),
    ]

    kept = without_thinking(history=history)

    response = kept[1]
    assert isinstance(response, ModelResponse)
    assert [type(part) for part in response.parts] == [TextPart, ToolCallPart]
    assert kept[0] == history[0]


def test_a_response_that_held_only_thinking_is_dropped() -> None:
    """An empty response would be sent as an empty assistant turn."""
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="start")]),
        ModelResponse(parts=[ThinkingPart(content="planning", provider_name="openai")]),
        ModelRequest(parts=[UserPromptPart(content="continue")]),
    ]

    kept = without_thinking(history=history)

    assert kept == [history[0], history[2]]
