"""Message-history cleanup applied before each model request.

Wired into the pydantic-ai agent via ``capabilities=[ProcessHistory(...)]``. The
full message history is re-sent on every model request, so two always-on
transforms shrink it without losing information the agent still holds:

1. Dedup ``read_channel`` messages already delivered in an earlier ``read_channel``
   result — each channel message survives only in its earliest read.
2. Drop empty ``read_notifications`` poll round-trips (``no_activity``), which carry
   no signal but accumulate in the hundreds.

Both transforms preserve tool-call/tool-return pairing and request/response
alternation, and are idempotent (safe to re-run on every request).
"""

import json
from dataclasses import replace
from typing import Any, NamedTuple, cast

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)

from schmidt.runtime.activity_notification import NotificationType

_READ_CHANNEL = "read_channel"
_READ_NOTIFICATIONS = "read_notifications"


class _ParsedContent(NamedTuple):
    """A tool return's content parsed as a mapping, plus how to re-serialize it."""

    payload: dict[str, Any] | None
    from_json_string: bool


class _ChannelMessageKey(NamedTuple):
    """Identity of a channel message for cross-call dedup."""

    round_number: Any
    sender: Any
    text: Any
    elapsed_seconds: Any


def clean_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Return the history with empty notification polls dropped and channel reads deduped."""
    without_empty_polls = _drop_empty_notification_units(messages=messages)
    return _dedup_read_channel_messages(messages=without_empty_polls)


def _parse_tool_return_content(content: object) -> _ParsedContent:
    """Parse a tool return's content into a mapping regardless of str/dict form."""
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return _ParsedContent(payload=None, from_json_string=True)
        if isinstance(parsed, dict):
            return _ParsedContent(payload=cast(dict[str, Any], parsed), from_json_string=True)
        return _ParsedContent(payload=None, from_json_string=True)
    if isinstance(content, dict):
        return _ParsedContent(payload=cast(dict[str, Any], content), from_json_string=False)
    return _ParsedContent(payload=None, from_json_string=False)


def _serialize_content(payload: dict[str, Any], from_json_string: bool) -> object:
    """Re-serialize a mapping back to the content form it came in as."""
    if from_json_string:
        return json.dumps(payload)
    return payload


def _tool_call_parts(response: ModelResponse) -> list[ToolCallPart]:
    """Return the tool-call parts of a response."""
    return [part for part in response.parts if isinstance(part, ToolCallPart)]


def _is_solo_notification_response(response: ModelResponse) -> bool:
    """True when the response's only tool call is a read_notifications call."""
    calls = _tool_call_parts(response=response)
    if len(calls) != 1:
        return False
    return calls[0].tool_name.endswith(_READ_NOTIFICATIONS)


def _is_no_activity_return(part: ToolReturnPart) -> bool:
    """True when a read_notifications return reports no activity."""
    if not part.tool_name.endswith(_READ_NOTIFICATIONS):
        return False
    parsed = _parse_tool_return_content(content=part.content)
    if parsed.payload is None:
        return False
    return parsed.payload.get("type") == NotificationType.NO_ACTIVITY.value


def _is_solo_no_activity_request(request: ModelRequest, call_id: str) -> bool:
    """True when the request is exactly one no_activity return matching ``call_id``."""
    if len(request.parts) != 1:
        return False
    part = request.parts[0]
    if not isinstance(part, ToolReturnPart):
        return False
    if part.tool_call_id != call_id:
        return False
    return _is_no_activity_return(part=part)


def _drop_empty_notification_units(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Drop each (response, return) unit whose sole action was an empty notification poll.

    Removes the whole two-message unit (assistant tool call + its no_activity
    return) so request/response alternation and tool-call pairing stay intact.
    The final unit is never dropped, so the turn the model is about to answer is
    left untouched.
    """
    result: list[ModelMessage] = []
    count = len(messages)
    index = 0
    while index < count:
        message = messages[index]
        has_following_non_final = index + 1 < count and index + 1 != count - 1
        if (
            has_following_non_final
            and isinstance(message, ModelResponse)
            and _is_solo_notification_response(response=message)
        ):
            following = messages[index + 1]
            call_id = _tool_call_parts(response=message)[0].tool_call_id
            if isinstance(following, ModelRequest) and _is_solo_no_activity_request(
                request=following,
                call_id=call_id,
            ):
                index += 2
                continue
        result.append(message)
        index += 1
    return result


def _channel_message_key(message: dict[str, Any]) -> _ChannelMessageKey:
    """Build the dedup key for one channel message entry."""
    return _ChannelMessageKey(
        round_number=message.get("round"),
        sender=message.get("sender"),
        text=message.get("text"),
        elapsed_seconds=message.get("elapsed_seconds"),
    )


def _dedup_channel_return(
    part: ToolReturnPart,
    seen: set[_ChannelMessageKey],
) -> ToolReturnPart:
    """Return a read_channel return with already-seen messages removed."""
    parsed = _parse_tool_return_content(content=part.content)
    if parsed.payload is None:
        return part
    raw_messages = parsed.payload.get("messages")
    if not isinstance(raw_messages, list):
        return part
    kept: list[Any] = []
    changed = False
    for entry in cast(list[Any], raw_messages):
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        key = _channel_message_key(message=cast(dict[str, Any], entry))
        if key in seen:
            changed = True
            continue
        seen.add(key)
        kept.append(entry)
    if not changed:
        return part
    new_payload = dict(parsed.payload)
    new_payload["messages"] = kept
    return replace(
        part,
        content=_serialize_content(payload=new_payload, from_json_string=parsed.from_json_string),
    )


def _dedup_read_channel_messages(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Drop channel messages from each read_channel return that an earlier read delivered."""
    seen: set[_ChannelMessageKey] = set()
    result: list[ModelMessage] = []
    for message in messages:
        if not isinstance(message, ModelRequest):
            result.append(message)
            continue
        new_parts: list[Any] = []
        changed = False
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name.endswith(_READ_CHANNEL):
                deduped = _dedup_channel_return(part=part, seen=seen)
                new_parts.append(deduped)
                if deduped is not part:
                    changed = True
            else:
                new_parts.append(part)
        if changed:
            result.append(replace(message, parts=new_parts))
        else:
            result.append(message)
    return result
