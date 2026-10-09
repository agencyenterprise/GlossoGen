"""``LLMResponseReceived.stop_reason`` is a closed set with the recorded spellings."""

from glossogen.models.event import LLMResponseReceived, StopReason
from glossogen.models.event_base import TokenUsage


def test_stop_reason_round_trips_through_json() -> None:
    event = LLMResponseReceived(
        round_number=1,
        agent_id="a",
        text="hi",
        tool_calls=[],
        stop_reason=StopReason.END_TURN,
        usage=TokenUsage(
            input_tokens=1,
            output_tokens=1,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )
    assert '"stop_reason":"end_turn"' in event.model_dump_json()
    reparsed = LLMResponseReceived.model_validate_json(event.model_dump_json())
    assert reparsed.stop_reason is StopReason.END_TURN
    assert reparsed.stop_reason == "end_turn"
