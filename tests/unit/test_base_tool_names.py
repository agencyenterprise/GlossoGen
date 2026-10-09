"""The base tool names are spelled once and shared by every module that matches on them."""

from glossogen.message_history_builder import CHANNEL_SCOPED_TOOLS
from glossogen.runtime.communication_tools import (
    BASE_TOOL_NAMES,
    GET_CHANNEL_MEMBERS_TOOL_NAME,
    LIST_CHANNELS_TOOL_NAME,
    READ_CHANNEL_TOOL_NAME,
    SEND_MESSAGE_TOOL_NAME,
)
from glossogen.runtime.read_notifications_schema import READ_NOTIFICATIONS_TOOL_NAME
from glossogen.testing.smoke_scenario import BASE_TOOLS


def test_base_tool_names_are_the_wire_spellings() -> None:
    assert BASE_TOOL_NAMES == frozenset(
        {
            "read_notifications",
            "read_channel",
            "send_message",
            "list_channels",
            "get_channel_members",
        }
    )
    assert set(BASE_TOOLS) == BASE_TOOL_NAMES
    assert CHANNEL_SCOPED_TOOLS == frozenset({SEND_MESSAGE_TOOL_NAME, READ_CHANNEL_TOOL_NAME})
    assert {
        READ_NOTIFICATIONS_TOOL_NAME,
        READ_CHANNEL_TOOL_NAME,
        SEND_MESSAGE_TOOL_NAME,
        LIST_CHANNELS_TOOL_NAME,
        GET_CHANNEL_MEMBERS_TOOL_NAME,
    } == BASE_TOOL_NAMES
