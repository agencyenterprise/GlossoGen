"""Which prompt an agent's cycle opens with, given the history it starts from.

A rebuilt resume history often ends in a request holding tool results, and the
runner follows it with the continuation prompt. A transferred history ends in a
request holding the message that opens the run, which must be sent as it is: a
continuation prompt after it would tell the agent to carry on a session it was
just told had ended.
"""

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from glossogen.runners.pydantic_ai_runner import (
    _cycle_start_checkpoint,  # pyright: ignore[reportPrivateUsage]
)

INITIAL = "initial prompt"
CONTINUATION = "continuation prompt"


def opening_prompt_of(*, history: list[ModelMessage] | None) -> str | None:
    """The prompt a cycle starting from ``history`` opens with."""
    return _cycle_start_checkpoint(
        history=history, initial=INITIAL, continuation=CONTINUATION
    ).prompt


def test_no_history_opens_on_the_initial_prompt() -> None:
    """A fresh agent has nothing to continue."""
    assert opening_prompt_of(history=None) == INITIAL


def test_a_history_ending_in_a_reply_opens_on_the_continuation_prompt() -> None:
    """The agent finished its last cycle with text."""
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=INITIAL)]),
        ModelResponse(parts=[TextPart(content="idle")]),
    ]

    assert opening_prompt_of(history=history) == CONTINUATION


def test_a_history_ending_in_tool_results_opens_on_the_continuation_prompt() -> None:
    """A rebuilt resume history cut after a tool call keeps the continuation prompt."""
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=INITIAL)]),
        ModelResponse(parts=[ToolCallPart(tool_name="read_notifications", tool_call_id="c1")]),
        ModelRequest(
            parts=[ToolReturnPart(tool_name="read_notifications", content="{}", tool_call_id="c1")]
        ),
    ]

    assert opening_prompt_of(history=history) == CONTINUATION


def test_a_history_ending_in_a_user_prompt_is_sent_as_it_is() -> None:
    """A transferred history's opening message is the agent's next request."""
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content=INITIAL)]),
        ModelResponse(parts=[TextPart(content="done")]),
        ModelRequest(parts=[UserPromptPart(content="the new run's prompts")]),
    ]

    assert opening_prompt_of(history=history) is None
