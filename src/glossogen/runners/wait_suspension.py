"""What the runner exchanges with a ``workspace_action`` agent around a suspension.

The model calls ``wait_for_message`` or ``finish``, whose schemas the MCP server
advertises. The runner intercepts the call before any tool executes, registers
the agent with the runtime's wait registry, and later answers the call with a
wake package. This module holds the argument models, the wake package model, and
the message construction for both the wake and the rejection of a response that
mixed a suspension call with other calls.
"""

import json
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from glossogen.models.interaction_protocol import WaitKind
from glossogen.runners.communication_protocol import (
    FINISH_TOOL_NAME,
    WAIT_FOR_MESSAGE_TOOL_NAME,
)
from glossogen.runtime.activity_notification import (
    ActivityNotification,
    DoneNotification,
    NewInfoNotification,
    NewMessagesNotification,
    NotificationType,
)
from glossogen.runtime.agent_session import AgentSession
from glossogen.runtime.wait_registry import WakeReason

SUSPEND_TOOL_NAMES = frozenset({WAIT_FOR_MESSAGE_TOOL_NAME, FINISH_TOOL_NAME})

MIXED_WAIT_ERROR = (
    "Rejected: wait_for_message and finish must be the only tool call in a response. "
    "None of this response's calls were executed. Issue your other calls first, read "
    "their results, then call wait_for_message or finish by itself."
)


class MessageWaitArguments(BaseModel):
    """The arguments a model passes to ``wait_for_message``."""

    model_config = ConfigDict(extra="forbid")
    timeout_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class FinishArguments(BaseModel):
    """The arguments a model passes to ``finish``; ``note`` is accepted and ignored."""

    model_config = ConfigDict(extra="forbid")
    note: str | None = None


class WaitRequest(NamedTuple):
    """A validated suspension call: what resumes the agent, and its optional deadline."""

    kind: WaitKind
    deadline_s: float | None


class LifecycleEntry(BaseModel):
    """One notification drained from the agent's queue at wake-up."""

    type: str
    text: str | None
    reason: str | None


class WakePackage(BaseModel):
    """What a resumed agent receives as its suspension call's result."""

    wake_reasons: list[str]
    round: int
    waited_seconds: float
    workspace: str | None
    lifecycle: list[LifecycleEntry]

    @property
    def terminated(self) -> bool:
        """True when the run ended while the agent was parked."""
        return any(entry.type == NotificationType.DONE.value for entry in self.lifecycle)


def tool_calls_of(response: ModelResponse) -> list[ToolCallPart]:
    """The tool calls a model response carries, in order."""
    return [part for part in response.parts if isinstance(part, ToolCallPart)]


def contains_wait_call(response: ModelResponse) -> bool:
    """True when the response contains a ``wait_for_message`` or ``finish`` call."""
    return any(part.tool_name in SUSPEND_TOOL_NAMES for part in tool_calls_of(response))


def parse_wait_arguments(part: ToolCallPart) -> WaitRequest:
    """Validate a suspension call's arguments; raises ``ValueError`` describing a bad call."""
    try:
        if part.tool_name == FINISH_TOOL_NAME:
            FinishArguments.model_validate(part.args_as_dict())
            return WaitRequest(kind="finish", deadline_s=None)
        arguments = MessageWaitArguments.model_validate(part.args_as_dict())
        return WaitRequest(kind="message", deadline_s=arguments.timeout_s)
    except ValidationError as exc:
        raise ValueError(
            f"{part.tool_name} arguments are invalid: {exc.errors(include_url=False)}"
        ) from exc


def drain_lifecycle(session: AgentSession) -> list[LifecycleEntry]:
    """Take every queued notification off the session without blocking.

    A parked agent's lifecycle events (its next task card, the run's end) queue on
    the session while it sleeps; the wake package carries them all, in order, and
    the queue is empty afterwards. Generic new-message pointers are dropped: the
    messages themselves are in the workspace part of the package.
    """
    entries: list[LifecycleEntry] = []
    while session.has_pending_notifications():
        notification = session.pop_notification()
        entry = _lifecycle_entry(notification=notification)
        if entry is not None:
            entries.append(entry)
    if session.terminated and not any(
        entry.type == NotificationType.DONE.value for entry in entries
    ):
        entries.append(
            LifecycleEntry(type=NotificationType.DONE.value, text=None, reason=session.done_reason)
        )
    return entries


def _lifecycle_entry(notification: ActivityNotification) -> LifecycleEntry | None:
    """Render one notification for the wake package, or None for a message pointer."""
    if isinstance(notification, NewInfoNotification):
        return LifecycleEntry(type=notification.type.value, text=notification.text, reason=None)
    if isinstance(notification, DoneNotification):
        return LifecycleEntry(type=notification.type.value, text=None, reason=notification.reason)
    if isinstance(notification, NewMessagesNotification):
        return None
    return LifecycleEntry(type=notification.type.value, text=notification.detail, reason=None)


def build_wake_package(
    reasons: list[WakeReason],
    round_number: int,
    waited_seconds: float,
    workspace: str | None,
    lifecycle: list[LifecycleEntry],
) -> WakePackage:
    """Assemble the package from the registry's signal and the scenario's observation."""
    return WakePackage(
        wake_reasons=[reason.value for reason in reasons],
        round=round_number,
        waited_seconds=round(waited_seconds, 3),
        workspace=workspace,
        lifecycle=lifecycle,
    )


def wake_return_request(tool_call: ToolCallPart, package: WakePackage) -> ModelRequest:
    """The request that answers the intercepted suspension call with its wake package."""
    return ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name=tool_call.tool_name,
                content=package.model_dump(),
                tool_call_id=tool_call.tool_call_id,
            )
        ]
    )


def error_return_request(tool_calls: list[ToolCallPart], error: str) -> ModelRequest:
    """The request that answers every call in a rejected response with ``error``."""
    return ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name=tool_call.tool_name,
                content=error,
                tool_call_id=tool_call.tool_call_id,
            )
            for tool_call in tool_calls
        ]
    )


def package_json(package: WakePackage) -> str:
    """The wake package as the text logged, and shown after an implicit finish."""
    return json.dumps(package.model_dump())
