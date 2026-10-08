"""The ``read_notifications`` tool's name, description and argument schema.

The agent runner builds the tool; the supervisor records its definition on
``AgentRegistered`` with the other tools'. Both read it from here.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from glossogen.models.tool_definition import RecordedToolDefinition
from glossogen.runtime.wait_for import WaitFor

READ_NOTIFICATIONS_TOOL_NAME = "read_notifications"

READ_NOTIFICATIONS_DESCRIPTION = (
    "Wait for activity, then return it: new messages, events, or status. "
    "wait_for='any' (the default) returns the next notification, or no_activity "
    "after a timeout. wait_for='message' suspends you until a teammate's message "
    "arrives or the next round's briefing does. wait_for='next_round' declares you "
    "finished with this round and suspends you until the next briefing. timeout_s "
    "wakes you after that many seconds. Must be called on its own, not alongside "
    "another tool call: issue any other tool calls first, see their results, then "
    "call read_notifications. The response includes a pending_count field "
    "indicating how many additional notifications are still queued. If "
    "pending_count > 0, call read_notifications again after handling the current "
    "one to drain the queue."
)


def _without_description(schema: dict[str, Any]) -> None:
    """Keep the class docstring, which is for developers, out of the schema the model reads."""
    schema.pop("description", None)


class ReadNotificationsArguments(BaseModel):
    """The arguments a model passes to ``read_notifications``.

    Its JSON schema is the tool's input schema, so the defaults here are what a
    model gets when it omits an argument.
    """

    model_config = ConfigDict(
        extra="forbid",
        title="read_notificationsArguments",
        json_schema_extra=_without_description,
    )
    wait_for: Literal["any", "message", "next_round"] = "any"
    timeout_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @property
    def wait_kind(self) -> WaitFor:
        """``wait_for`` as the enum the runtime uses."""
        return WaitFor(self.wait_for)


def read_notifications_tool_definition(description: str) -> RecordedToolDefinition:
    """The tool's name, ``description`` and input schema, as recorded on ``AgentRegistered``."""
    return RecordedToolDefinition(
        name=READ_NOTIFICATIONS_TOOL_NAME,
        description=description,
        input_schema=ReadNotificationsArguments.model_json_schema(),
    )
