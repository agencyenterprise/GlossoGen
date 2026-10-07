"""A wake package carrying a lifecycle notification is pinned like a notification poll."""

import json

import pytest
from pydantic_ai.messages import ToolReturnPart

from glossogen.runners.history_cleanup_processor import notification_type_of


def wait_return(lifecycle: list[dict[str, str | None]]) -> ToolReturnPart:
    package = {
        "wake_reasons": ["lifecycle"],
        "round": 2,
        "waited_seconds": 1.5,
        "workspace": "Depot now (v3): r1=1",
        "lifecycle": lifecycle,
    }
    return ToolReturnPart("wait_for_message", json.dumps(package), "call-wait")


@pytest.mark.parametrize("tool_name", ["wait_for_message", "finish"])
def test_a_wake_with_a_task_card_reads_as_new_info(tool_name: str) -> None:
    part = wait_return([{"type": "new_info", "text": "Round 2. TEAM TASK", "reason": None}])
    part.tool_name = tool_name
    assert notification_type_of(part=part) == "new_info"


def test_done_wins_over_other_lifecycle_entries():
    part = wait_return(
        [
            {"type": "new_info", "text": "card", "reason": None},
            {"type": "done", "text": None, "reason": "scenario_complete"},
        ]
    )
    assert notification_type_of(part=part) == "done"


def test_a_wake_without_lifecycle_is_an_ordinary_return():
    assert notification_type_of(part=wait_return([])) is None
    assert notification_type_of(part=ToolReturnPart("finish", "not json", "call-wait")) is None
    assert (
        notification_type_of(part=ToolReturnPart("act", json.dumps({"type": "done"}), "c")) is None
    )
