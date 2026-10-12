"""Turns the app server's notifications into ``SessionItem``s.

The thread is started with raw events on, so every model response arrives as
its output items (``rawResponseItem/completed``: assistant message, reasoning,
function call) followed by ``rawResponse/completed`` with that response's usage.
Raw items carry no response id, so a response is numbered within its turn, and
it opens with the first output item after the previous one closed.

Codex starts running a response's first tool call before the rest of the
response has streamed, and keeps reading the stream while the call is pending;
the session runner relies on both. A call's result is read off the completed
``dynamicToolCall`` item.

The payload models follow the app server's published schema, including the
fields it allows to be null or absent: a response may complete with no usage,
which is logged as zero tokens with a warning.

A request whose stream fails is reported with an ``error`` notification, and
Codex may retry it. Codex sends that notification only after the request's
pending calls have returned, and the retried request carries their outputs. The
response it left open is abandoned, so the retry opens a response of its own
rather than merging into it. A compaction is reported as
a completed ``contextCompaction`` item; the request that produced it completes
as a response with no output, logged for its usage. Function-call arguments the
model wrote as invalid JSON are kept as the raw string: Codex runs no call and
answers the model itself, with a raw ``function_call_output``. That output is
read as the call's result, since nothing else will report one.
"""

import json
import logging
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from glossogen.models.event_base import TokenUsage
from glossogen.runners.codex_app_server.app_server_connection import ServerNotification
from glossogen.runners.session_harness.seat_session import (
    CompactionBoundary,
    CycleEnded,
    ResponseAbandoned,
    ResponseCompleted,
    ResponseStarted,
    SessionItem,
    TextChunk,
    ThinkingChunk,
    ToolResultChunk,
    ToolUseChunk,
)

logger = logging.getLogger(__name__)

THINKING_PROVIDER_NAME = "openai"
TOOL_USE_STOP_REASON = "tool_use"
END_TURN_STOP_REASON = "end_turn"
FAILED_TURN_STATUSES = frozenset({"failed", "interrupted"})
UNPARSED_ARGUMENTS_KEY = "unparsed_arguments"


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class _ContentPart(_Lenient):
    type: str
    text: str = ""


class _RawItem(_Lenient):
    type: str
    role: str | None = None
    name: str | None = None
    arguments: str | None = None
    call_id: str | None = None
    content: list[_ContentPart] | None = None
    summary: list[_ContentPart] | None = None
    output: str | list[_ContentPart] | None = None


class _RawItemParams(_Lenient):
    turn_id: str = Field(alias="turnId")
    item: _RawItem


class _CodexUsage(_Lenient):
    input_tokens: int = Field(alias="inputTokens")
    cached_input_tokens: int = Field(alias="cachedInputTokens")
    cache_write_input_tokens: int = Field(default=0, alias="cacheWriteInputTokens")
    output_tokens: int = Field(alias="outputTokens")


class _RawResponseParams(_Lenient):
    turn_id: str = Field(alias="turnId")
    usage: _CodexUsage | None = None


class _ToolOutputItem(_Lenient):
    type: str
    text: str = ""


class _ThreadItem(_Lenient):
    type: str
    id: str
    content_items: list[_ToolOutputItem] | None = Field(default=None, alias="contentItems")


class _ItemCompletedParams(_Lenient):
    item: _ThreadItem


class _ErrorParams(_Lenient):
    turn_id: str = Field(alias="turnId")
    will_retry: bool = Field(alias="willRetry")


class _TurnError(_Lenient):
    message: str


class _Turn(_Lenient):
    id: str
    status: str
    error: _TurnError | None = None


class _TurnCompletedParams(_Lenient):
    thread_id: str = Field(alias="threadId")
    turn: _Turn


class CodexItemTranslator:
    """Translates one thread's notifications, numbering its responses within each turn."""

    def __init__(self) -> None:
        self._turn_id = ""
        self._responses_in_turn = 0
        self._open_message_id: str | None = None
        self._open_has_calls = False
        self._calls_codex_answers: set[str] = set()

    def translate(self, notification: ServerNotification) -> list[SessionItem]:
        """The items one notification carries; ones the runner has no use for carry none."""
        method = notification.method
        params = notification.params
        if method == "rawResponseItem/completed":
            return self._raw_item(params=_RawItemParams.model_validate(params))
        if method == "rawResponse/completed":
            return self._response_completed(params=_RawResponseParams.model_validate(params))
        if method == "item/completed":
            return _completed_item(params=_ItemCompletedParams.model_validate(params))
        if method == "error":
            return self._abandon_open_response(params=_ErrorParams.model_validate(params))
        if method == "turn/completed":
            return [self._turn_completed(params=_TurnCompletedParams.model_validate(params))]
        return []

    def _raw_item(self, params: _RawItemParams) -> list[SessionItem]:
        item = params.item
        if item.type == "message" and item.role == "assistant":
            items = self._open(turn_id=params.turn_id)
            text = "".join(part.text for part in _parts(item.content) if part.type == "output_text")
            items.append(TextChunk(message_id=self._current_message_id(), text=text))
            return items
        if item.type == "reasoning":
            items = self._open(turn_id=params.turn_id)
            summary = "\n".join(part.text for part in _parts(item.summary))
            if summary:
                items.append(
                    ThinkingChunk(
                        message_id=self._current_message_id(),
                        thinking=summary,
                        signature=None,
                        provider_name=THINKING_PROVIDER_NAME,
                    )
                )
            return items
        if item.type == "function_call":
            return self._function_call(item=item, turn_id=params.turn_id)
        if item.type == "function_call_output" and item.call_id in self._calls_codex_answers:
            self._calls_codex_answers.discard(item.call_id)
            return [ToolResultChunk(call_id=item.call_id, content=_output_text(output=item.output))]
        return []

    def _function_call(self, item: _RawItem, turn_id: str) -> list[SessionItem]:
        """A call the response made; one Codex will answer itself is remembered."""
        items = self._open(turn_id=turn_id)
        self._open_has_calls = True
        call_id = _required(value=item.call_id, field="call_id")
        arguments = _arguments(raw=item.arguments)
        answered_by_codex = UNPARSED_ARGUMENTS_KEY in arguments
        if answered_by_codex:
            self._calls_codex_answers.add(call_id)
        items.append(
            ToolUseChunk(
                message_id=self._current_message_id(),
                call_id=call_id,
                tool_name=_required(value=item.name, field="name"),
                arguments=arguments,
                answered_by_cli=answered_by_codex,
            )
        )
        return items

    def _response_completed(self, params: _RawResponseParams) -> list[SessionItem]:
        items = self._open(turn_id=params.turn_id)
        stop_reason = END_TURN_STOP_REASON
        if self._open_has_calls:
            stop_reason = TOOL_USE_STOP_REASON
        items.append(
            ResponseCompleted(
                message_id=self._current_message_id(),
                stop_reason=stop_reason,
                usage=_token_usage(usage=params.usage, message_id=self._current_message_id()),
            )
        )
        self._open_message_id = None
        self._open_has_calls = False
        return items

    def _abandon_open_response(self, params: _ErrorParams) -> list[SessionItem]:
        """Give up on the response a failed request left open, if any."""
        logger.warning(
            "Codex reported a failed request in turn %s (will retry: %s)",
            params.turn_id,
            params.will_retry,
        )
        if self._open_message_id is None or params.turn_id != self._turn_id:
            return []
        abandoned = ResponseAbandoned(message_id=self._open_message_id)
        self._open_message_id = None
        self._open_has_calls = False
        return [abandoned]

    def _turn_completed(self, params: _TurnCompletedParams) -> CycleEnded:
        turn = params.turn
        self._open_message_id = None
        self._open_has_calls = False
        is_error = turn.status in FAILED_TURN_STATUSES
        error_text = ""
        if is_error:
            error_text = turn.status
            if turn.error is not None:
                error_text = turn.error.message
        return CycleEnded(
            session_id=params.thread_id,
            is_error=is_error,
            error_text=error_text,
            reported_cost_usd=None,
        )

    def _open(self, turn_id: str) -> list[SessionItem]:
        """Open a response unless one is open; the items that announce it."""
        if turn_id != self._turn_id:
            self._turn_id = turn_id
            self._responses_in_turn = 0
            self._open_message_id = None
        if self._open_message_id is not None:
            return []
        self._responses_in_turn += 1
        self._open_message_id = f"{turn_id}-response-{self._responses_in_turn}"
        self._open_has_calls = False
        return [ResponseStarted(message_id=self._open_message_id)]

    def _current_message_id(self) -> str:
        if self._open_message_id is None:
            raise RuntimeError("no response is open")
        return self._open_message_id


def _output_text(output: str | list[_ContentPart] | None) -> str:
    """A raw ``function_call_output``'s text, whether a string or a list of parts."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    return "".join(part.text for part in output)


def _parts(parts: list[_ContentPart] | None) -> list[_ContentPart]:
    """An item's content parts; the schema allows a null list."""
    if parts is None:
        return []
    return parts


def _token_usage(usage: _CodexUsage | None, message_id: str) -> TokenUsage:
    """A response's usage, or zero tokens when the server reported none."""
    if usage is None:
        logger.warning("Codex reported no usage for response %s; logging zero tokens", message_id)
        return TokenUsage(
            input_tokens=0,
            output_tokens=0,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
    return TokenUsage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_input_tokens=usage.cached_input_tokens,
        cache_creation_input_tokens=usage.cache_write_input_tokens,
    )


def _completed_item(params: _ItemCompletedParams) -> list[SessionItem]:
    """A client-defined tool call's result, or a compaction; other items carry nothing."""
    item = params.item
    if item.type == "contextCompaction":
        return [CompactionBoundary(details={"type": item.type, "id": item.id})]
    if item.type != "dynamicToolCall":
        return []
    content_items: list[_ToolOutputItem] = []
    if item.content_items is not None:
        content_items = item.content_items
    return [
        ToolResultChunk(
            call_id=item.id,
            content="".join(part.text for part in content_items if part.type == "inputText"),
        )
    ]


def _arguments(raw: str | None) -> dict[str, Any]:
    """A function call's arguments, which Codex sends as a JSON string.

    Arguments that are not a JSON object are kept as the raw string under
    ``UNPARSED_ARGUMENTS_KEY``, since the model wrote them and Codex runs no call.
    """
    if raw is None or raw.strip() == "":
        return {}
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("A Codex function call's arguments are not valid JSON: %r", raw)
        return {UNPARSED_ARGUMENTS_KEY: raw}
    if not isinstance(parsed, dict):
        logger.warning("A Codex function call's arguments are not an object: %r", raw)
        return {UNPARSED_ARGUMENTS_KEY: raw}
    return cast(dict[str, Any], parsed)


def _required(value: str | None, field: str) -> str:
    if value is None:
        raise ValueError(f"a function call item has no {field}")
    return value
