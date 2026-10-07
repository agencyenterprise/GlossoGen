"""Self-hosted history trimming: what is dropped first, and what is never dropped.

The history below mirrors a workspace agent: one lifecycle poll that delivered
the private card, then many act calls, each preceded by long reasoning. The
last response reports server usage, which is what the budget is priced from.
"""

import json

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import RequestUsage

from glossogen.runners.context_budget_processor import (
    RECENT_MESSAGES_KEPT,
    TRIMMED_TOOL_RESULT,
    ContextBudgetTrimmer,
)

CARD = json.dumps({"type": "new_info", "text": "YOUR PRIVATE TASK: retain r956917"})
DEPOT = "Depot v3: " + ", ".join(f"r{n:06d}={n % 7}" for n in range(60))
REASONING = "Okay, let me recap the current situation. " * 40


def workspace_history(act_calls: int, reported_input_tokens: int) -> list[ModelMessage]:
    """A card delivery followed by ``act_calls`` reasoning + act steps."""
    messages: list[ModelMessage] = [
        ModelRequest(parts=[SystemPromptPart("rules"), UserPromptPart("start")]),
        ModelResponse(parts=[ToolCallPart("read_notifications", {}, "card")]),
        ModelRequest(parts=[ToolReturnPart("read_notifications", CARD, "card")]),
    ]
    for index in range(act_calls):
        call_id = f"act{index}"
        messages.append(
            ModelResponse(
                parts=[
                    ThinkingPart(REASONING),
                    ToolCallPart("act", {"command": "depot"}, call_id),
                ]
            )
        )
        messages.append(ModelRequest(parts=[ToolReturnPart("act", DEPOT, call_id)]))
    last = messages[-2]
    assert isinstance(last, ModelResponse)
    last.usage = RequestUsage(input_tokens=reported_input_tokens, output_tokens=200)
    return messages


def thinking_count(messages: list[ModelMessage]) -> int:
    return sum(
        isinstance(part, ThinkingPart)
        for message in messages
        if isinstance(message, ModelResponse)
        for part in message.parts
    )


def tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


def test_history_under_budget_is_returned_unchanged():
    messages = workspace_history(act_calls=5, reported_input_tokens=4_000)
    trimmer = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=True
    )
    assert trimmer.trim(messages) is messages


def test_old_reasoning_goes_first_and_the_latest_is_kept():
    messages = workspace_history(act_calls=20, reported_input_tokens=21_000)
    trimmed = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=True
    ).trim(messages)
    assert thinking_count(messages) == 20
    assert thinking_count(trimmed) == 1
    assert isinstance(trimmed[-2], ModelResponse)
    assert isinstance(trimmed[-2].parts[0], ThinkingPart)
    # Removing reasoning was enough, so no observation was touched.
    assert all(part.content != TRIMMED_TOOL_RESULT for part in tool_returns(trimmed))


def test_old_tool_results_are_trimmed_but_the_card_and_recent_steps_survive():
    messages = workspace_history(act_calls=30, reported_input_tokens=80_000)
    trimmed = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=True
    ).trim(messages)
    returns = tool_returns(trimmed)
    assert returns[0].content == CARD
    assert any(part.content == TRIMMED_TOOL_RESULT for part in returns)
    recent = trimmed[-RECENT_MESSAGES_KEPT:]
    assert all(part.content == DEPOT for part in tool_returns(recent))
    # Every tool call still has its return, in the same order.
    calls = [
        part.tool_call_id
        for message in trimmed
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    assert calls == [part.tool_call_id for part in returns]
    assert len(trimmed) == len(messages)


def test_trimming_is_idempotent():
    messages = workspace_history(act_calls=30, reported_input_tokens=80_000)
    trimmer = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=True
    )
    once = trimmer.trim(messages)
    twice = trimmer.trim(once)
    assert [m.parts for m in twice] == [m.parts for m in once]


def test_a_response_holding_only_reasoning_is_not_emptied():
    messages = workspace_history(act_calls=20, reported_input_tokens=21_000)
    messages.insert(3, ModelResponse(parts=[ThinkingPart(REASONING)]))
    messages.insert(4, ModelRequest(parts=[UserPromptPart("continue")]))
    trimmed = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=True
    ).trim(messages)
    assert all(message.parts for message in trimmed)
    assert trimmed[3].parts == [ThinkingPart(REASONING)]


def test_reasoning_that_is_not_sent_back_is_priced_at_zero_and_left_alone():
    """With thinking off, the estimate ignores ThinkingParts and stripping them is no gain.

    The same history that trims twenty reasoning blocks above now sits under
    budget once reasoning costs nothing, and the reasoning stays in the stored
    history for the event log.
    """
    messages = workspace_history(act_calls=20, reported_input_tokens=21_000)
    for message in messages:
        if isinstance(message, ModelResponse):
            message.usage = RequestUsage()
    trimmer = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=False
    )
    assert trimmer.trim(messages) is messages

    # Over budget on observations alone: tool results go, reasoning does not.
    heavy = workspace_history(act_calls=30, reported_input_tokens=80_000)
    trimmed = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=False
    ).trim(heavy)
    assert thinking_count(trimmed) == 30
    assert any(part.content == TRIMMED_TOOL_RESULT for part in tool_returns(trimmed))


MESSAGE_BLOCK = "NEW PUBLIC MESSAGES\n[round 1; Crafter 2 via workspace] I will make r000123"


def history_with_delivery(result: object, tool_name: str) -> list[ModelMessage]:
    """A long workspace history whose first act result delivered a public message."""
    messages = workspace_history(act_calls=30, reported_input_tokens=80_000)
    delivering = messages[4]
    assert isinstance(delivering, ModelRequest)
    part = delivering.parts[0]
    assert isinstance(part, ToolReturnPart)
    messages[4] = ModelRequest(parts=[ToolReturnPart(tool_name, result, part.tool_call_id)])
    return messages


def test_a_trimmed_result_keeps_the_public_messages_it_delivered():
    messages = history_with_delivery(result=f"{DEPOT}\n\n{MESSAGE_BLOCK}", tool_name="act")
    trimmed = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=True
    ).trim(messages)
    content = tool_returns(trimmed)[1].content
    assert isinstance(content, str)
    assert content.startswith(TRIMMED_TOOL_RESULT)
    assert content.endswith(MESSAGE_BLOCK)
    assert DEPOT not in content


def test_messages_inside_json_results_are_kept():
    wake = json.dumps(
        {
            "wake_reasons": ["new_public_message"],
            "workspace": f"{DEPOT}\n\n{MESSAGE_BLOCK}",
            "lifecycle": [],
        }
    )
    conflict = {
        "status": "conflict",
        "new_messages": [{"round": 1, "sender": "Crafter 2", "text": "hold r000123"}],
    }
    for result, tool_name in ((wake, "wait"), (conflict, "send_message")):
        trimmed = ContextBudgetTrimmer(
            agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=True
        ).trim(history_with_delivery(result=result, tool_name=tool_name))
        content = tool_returns(trimmed)[1].content
        assert isinstance(content, str)
        assert content.startswith(TRIMMED_TOOL_RESULT)
        assert ("I will make r000123" in content) or ("hold r000123" in content)


def test_an_empty_message_block_is_not_kept():
    messages = history_with_delivery(
        result=f"{DEPOT}\n\nNEW PUBLIC MESSAGES\nnone", tool_name="act"
    )
    trimmed = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=True
    ).trim(messages)
    assert tool_returns(trimmed)[1].content == TRIMMED_TOOL_RESULT


def test_trimming_that_keeps_messages_is_idempotent():
    messages = history_with_delivery(result=f"{DEPOT}\n\n{MESSAGE_BLOCK}", tool_name="act")
    trimmer = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=True
    )
    once = trimmer.trim(messages)
    twice = trimmer.trim(once)
    assert [m.parts for m in twice] == [m.parts for m in once]


def test_a_briefing_delivered_again_is_pinned_only_in_its_latest_copy():
    messages = workspace_history(act_calls=30, reported_input_tokens=80_000)
    resent = json.dumps(
        {"type": "new_info", "text": "YOUR PRIVATE TASK: retain r956917", "pending_count": 0}
    )
    # Replace an old act step with a poll that re-sent the same card.
    messages[5] = ModelResponse(parts=[ToolCallPart("read_notifications", {}, "resend")])
    messages[6] = ModelRequest(parts=[ToolReturnPart("read_notifications", resent, "resend")])
    trimmed = ContextBudgetTrimmer(
        agent_id="crafter_3", token_threshold=20_000, thinking_in_requests=True
    ).trim(messages)
    returns = {part.tool_call_id: part.content for part in tool_returns(trimmed)}
    assert returns["card"] == TRIMMED_TOOL_RESULT
    assert returns["resend"] == resent
