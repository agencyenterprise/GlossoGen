"""The names of the base communication tools, as they appear in a run's log.

The runtime offers these tools and the runner builds them; replays and metrics
read these names to find the calls in a recorded history.
"""

from glossogen.models.read_notifications_schema import READ_NOTIFICATIONS_TOOL_NAME

READ_CHANNEL_TOOL_NAME = "read_channel"
SEND_MESSAGE_TOOL_NAME = "send_message"
LIST_CHANNELS_TOOL_NAME = "list_channels"
GET_CHANNEL_MEMBERS_TOOL_NAME = "get_channel_members"

BASE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        READ_NOTIFICATIONS_TOOL_NAME,
        READ_CHANNEL_TOOL_NAME,
        SEND_MESSAGE_TOOL_NAME,
        LIST_CHANNELS_TOOL_NAME,
        GET_CHANNEL_MEMBERS_TOOL_NAME,
    }
)
"""The tools every agent is offered unless the scenario withholds one."""
