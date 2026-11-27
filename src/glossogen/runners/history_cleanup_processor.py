"""Message-history cleanup applied before each model request.

Wired into the pydantic-ai agent via ``capabilities=[ProcessHistory(...)]``. The
full message history is re-sent on every model request, so two always-on
transforms shrink it without losing information the agent still holds:

1. Dedup ``read_channel`` messages already delivered in an earlier ``read_channel``
   result: each channel message survives only in its earliest read. A dropped
   drawing takes its attached image with it.
2. Drop empty ``read_notifications`` poll round-trips (``no_activity``), which carry
   no signal but accumulate in the hundreds.

Both transforms preserve tool-call/tool-return pairing and request/response
alternation, and are idempotent (safe to re-run on every request).
"""

import json
import logging
from dataclasses import replace
from typing import Any, NamedTuple, cast

from pydantic import ValidationError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)

from glossogen.models.canvas import ToolResultImage
from glossogen.models.communication_tool_names import READ_CHANNEL_TOOL_NAME
from glossogen.models.mcp_responses import ChannelMessage, ReadChannelResult
from glossogen.models.read_notifications_schema import READ_NOTIFICATIONS_TOOL_NAME
from glossogen.run_replay.tool_return_images import split_tool_return, tool_return_with_images
from glossogen.scenario_contract.notification_delivery import (
    DELIVERED_NOTIFICATION_ADAPTER,
    DeliveredNoActivity,
)

logger = logging.getLogger(__name__)


class _ParsedContent(NamedTuple):
    """A tool return's content parsed as a mapping, plus how to re-serialize it.

    ``images`` holds the images attached after the JSON when the content was
    built by ``tool_return_with_images``, and is ``None`` otherwise.
    """

    payload: dict[str, Any] | None
    from_json_string: bool
    images: list[ToolResultImage] | None


class _ChannelMessageKey(NamedTuple):
    """Identity of a channel message for cross-call dedup."""

    channel_id: str
    round_number: int
    sender: str
    text: str
    elapsed_seconds: float


def clean_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Return the history with empty notification polls dropped and channel reads deduped."""
    without_empty_polls = _drop_empty_notification_units(messages=messages)
    return _dedup_read_channel_messages(messages=without_empty_polls)


def _parse_tool_return_content(content: object) -> _ParsedContent:
    """Parse a tool return's content into a mapping regardless of str/dict/image-list form."""
    split = split_tool_return(content=content)
    if split is not None:
        return _parse_json_text(text=split.text, images=split.images)
    if isinstance(content, str):
        return _parse_json_text(text=content, images=None)
    if isinstance(content, dict):
        return _ParsedContent(
            payload=cast(dict[str, Any], content), from_json_string=False, images=None
        )
    return _ParsedContent(payload=None, from_json_string=False, images=None)


def _parse_json_text(text: str, images: list[ToolResultImage] | None) -> _ParsedContent:
    """Parse JSON text into a mapping, or no mapping when it holds something else."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError, ValueError:
        return _ParsedContent(payload=None, from_json_string=True, images=images)
    if isinstance(parsed, dict):
        return _ParsedContent(
            payload=cast(dict[str, Any], parsed), from_json_string=True, images=images
        )
    return _ParsedContent(payload=None, from_json_string=True, images=images)


def _serialize_content(payload: dict[str, Any], parsed: _ParsedContent) -> object:
    """Re-serialize a mapping back to the content form it came in as.

    Content that carried images keeps the images its messages still refer to.
    """
    if parsed.images is not None:
        referenced = _referenced_image_numbers(payload=payload)
        return tool_return_with_images(
            text=json.dumps(payload),
            images=[image for image in parsed.images if image.number in referenced],
        )
    if parsed.from_json_string:
        return json.dumps(payload)
    return payload


def _referenced_image_numbers(payload: dict[str, Any]) -> set[int]:
    """The image numbers the messages of a ``read_channel`` payload refer to."""
    numbers: set[int] = set()
    for entry in cast(list[Any], payload.get("messages", [])):
        if not isinstance(entry, dict):
            continue
        image = cast(dict[str, Any], entry).get("image")
        if isinstance(image, int):
            numbers.add(image)
    return numbers


def _tool_call_parts(response: ModelResponse) -> list[ToolCallPart]:
    """Return the tool-call parts of a response."""
    return [part for part in response.parts if isinstance(part, ToolCallPart)]


def _is_solo_notification_response(response: ModelResponse) -> bool:
    """True when the response is one read_notifications call plus optional reasoning."""
    calls = _tool_call_parts(response=response)
    if len(calls) != 1 or calls[0].tool_name != READ_NOTIFICATIONS_TOOL_NAME:
        return False
    return all(isinstance(part, (ThinkingPart, ToolCallPart)) for part in response.parts)


def _is_no_activity_return(part: ToolReturnPart) -> bool:
    """True when a read_notifications return reports no activity."""
    if part.tool_name != READ_NOTIFICATIONS_TOOL_NAME:
        return False
    parsed = _parse_tool_return_content(content=part.content)
    if parsed.payload is None:
        return False
    try:
        delivered = DELIVERED_NOTIFICATION_ADAPTER.validate_python(parsed.payload)
    except ValidationError:
        logger.debug(
            "read_notifications return %s is a scenario's own rendering", part.tool_call_id
        )
        return False
    return isinstance(delivered, DeliveredNoActivity)


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


def _channel_message_key(message: ChannelMessage, channel_id: str) -> _ChannelMessageKey:
    """Build the dedup key for one channel message entry."""
    return _ChannelMessageKey(
        channel_id=channel_id,
        round_number=message.round,
        sender=message.sender,
        text=message.text,
        elapsed_seconds=message.elapsed_seconds,
    )


def _dedup_channel_return(
    part: ToolReturnPart,
    channel_id: str,
    seen_counts: dict[_ChannelMessageKey, int],
) -> ToolReturnPart:
    """Return a read_channel return with already-seen messages removed.

    A return that is not a ``ReadChannelResult`` is left as it is.
    """
    parsed = _parse_tool_return_content(content=part.content)
    if parsed.payload is None:
        return part
    try:
        result = ReadChannelResult.model_validate(parsed.payload)
    except ValidationError:
        logger.exception("read_channel return %s is not a ReadChannelResult", part.tool_call_id)
        return part
    raw_entries = cast(list[Any], parsed.payload["messages"])
    kept: list[Any] = []
    current_counts: dict[_ChannelMessageKey, int] = {}
    changed = False
    for entry, message in zip(raw_entries, result.messages, strict=True):
        key = _channel_message_key(message=message, channel_id=channel_id)
        occurrence = current_counts.get(key, 0) + 1
        current_counts[key] = occurrence
        if occurrence <= seen_counts.get(key, 0):
            changed = True
            continue
        kept.append(entry)
    for key, count in current_counts.items():
        seen_counts[key] = max(seen_counts.get(key, 0), count)
    if not changed:
        return part
    new_payload = dict(parsed.payload)
    new_payload["messages"] = kept
    return replace(
        part,
        content=_serialize_content(payload=new_payload, parsed=parsed),
    )


def _dedup_read_channel_messages(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Drop channel messages from each read_channel return that an earlier read delivered."""
    seen_counts: dict[_ChannelMessageKey, int] = {}
    channel_by_call_id: dict[str, str] = {}
    result: list[ModelMessage] = []
    for message in messages:
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if not isinstance(part, ToolCallPart) or part.tool_name != READ_CHANNEL_TOOL_NAME:
                    continue
                channel_id = part.args_as_dict().get("channel_id")
                if isinstance(channel_id, str):
                    channel_by_call_id[part.tool_call_id] = channel_id
            result.append(message)
            continue
        new_parts: list[Any] = []
        changed = False
        for part in message.parts:
            channel_id = channel_by_call_id.get(getattr(part, "tool_call_id", ""))
            if (
                isinstance(part, ToolReturnPart)
                and part.tool_name == READ_CHANNEL_TOOL_NAME
                and channel_id is not None
            ):
                deduped = _dedup_channel_return(
                    part=part,
                    channel_id=channel_id,
                    seen_counts=seen_counts,
                )
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
