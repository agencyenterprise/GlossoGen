"""A response's exposed reasoning and its text become separate run-detail entries."""

from glossogen.models.event import LLMResponseReceived, StopReason
from glossogen.models.event_base import TokenUsage
from glossogen.models.thinking_part_record import ThinkingPartRecord
from glossogen.server.runs.models import ReasoningKind
from glossogen.server.runs.reasoning_entries import reasoning_entries_of

USAGE = TokenUsage(
    input_tokens=0,
    output_tokens=0,
    reasoning_tokens=0,
    cache_read_input_tokens=0,
    cache_creation_input_tokens=0,
)


def response(text: str | None, parts: list[str], thinking: str | None) -> LLMResponseReceived:
    return LLMResponseReceived(
        round_number=3,
        agent_id="player_a",
        thinking=thinking,
        thinking_parts=[
            ThinkingPartRecord(content=part, id=None, signature=None, provider_name="openai")
            for part in parts
        ],
        text=text,
        tool_calls=[],
        stop_reason=StopReason.TOOL_USE,
        usage=USAGE,
    )


def test_a_reasoning_model_with_no_text_still_gets_an_entry_from_its_summary() -> None:
    event = response(
        text=None, parts=["**Designing a code**", "**Decoding the reply**"], thinking=None
    )
    [entry] = reasoning_entries_of(event=event)
    assert entry.kind is ReasoningKind.THINKING
    assert entry.text == "**Designing a code**\n\n**Decoding the reply**"
    assert entry.message_id == event.event_id + ":thinking"
    assert (entry.sender_agent_id, entry.round_number) == ("player_a", 3)


def test_thinking_comes_before_text_and_each_keeps_its_own_id() -> None:
    event = response(text="I will move right.", parts=["Weighing the options"], thinking=None)
    thinking, text = reasoning_entries_of(event=event)
    assert (thinking.kind, text.kind) == (ReasoningKind.THINKING, ReasoningKind.TEXT)
    assert text.message_id == event.event_id
    assert text.text == "I will move right."


def test_a_log_with_only_the_joined_thinking_field_is_read_too() -> None:
    event = response(text=None, parts=[], thinking="  joined thinking  ")
    [entry] = reasoning_entries_of(event=event)
    assert entry.text == "joined thinking"


def test_blank_text_and_blank_thinking_give_no_entry() -> None:
    assert reasoning_entries_of(event=response(text="  ", parts=["  "], thinking=None)) == []
