"""History trimming that keeps a self-hosted agent's input under a token budget.

Self-hosted OpenAI-compatible servers (vLLM) have no provider-native compaction,
and a request whose input plus ``max_tokens`` exceeds the server's
``--max-model-len`` is rejected with a 400. ``ContextBudgetTrimmer`` is wired in as
a ``ProcessHistory`` capability when ``compaction.enabled`` is set for a
self-hosted agent. Once the estimated input exceeds ``token_threshold`` it trims,
in order, until the estimate fits:

1. Reasoning (``ThinkingPart``) from every response except the latest.
2. The content of tool results older than the most recent messages, except
   lifecycle notifications (``new_info`` task cards and ``done``; a briefing
   delivered again later is kept only in its latest copy). A trimmed result
   keeps the public message bodies it delivered, which no later result repeats.

Tool-call/tool-return pairing and request/response alternation are preserved,
and the transform is idempotent. pydantic-ai stores the processed history, so
trimmed content stays trimmed on later requests.
"""

import json
import logging
from dataclasses import replace
from typing import Any, cast

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)

from glossogen.models.public_message_block import PUBLIC_MESSAGES_HEADER, public_message_block
from glossogen.runners.history_cleanup_processor import notification_type_of
from glossogen.runtime.activity_notification import NotificationType

logger = logging.getLogger(__name__)

# Tokens per character when no server-reported usage is available yet. Qwen
# tokenizers split digits individually, so opaque IDs such as r264889 cost
# about one token per character; 0.4 errs toward over-estimating.
FALLBACK_TOKENS_PER_CHARACTER = 0.4
# Bounds on the ratio calibrated from server usage. The request's token count
# also covers tool schemas, which the history's characters do not.
MIN_TOKENS_PER_CHARACTER = 0.25
MAX_TOKENS_PER_CHARACTER = 1.0
# Tool results inside this many trailing messages are never trimmed, so the
# agent keeps its latest observations verbatim.
RECENT_MESSAGES_KEPT = 12
TRIMMED_TOOL_RESULT = "[older tool result removed to fit the context window]"
KEPT_MESSAGES_NOTE = "[public messages it delivered are kept below]"
_PINNED_NOTIFICATION_TYPES = frozenset(
    {NotificationType.NEW_INFO.value, NotificationType.DONE.value}
)


class _TokenEstimate:
    """Estimated input tokens for a history, and the ratio used to price edits."""

    def __init__(self, tokens: float, tokens_per_character: float) -> None:
        self.tokens = tokens
        self.tokens_per_character = tokens_per_character

    def subtract_characters(self, characters: int) -> None:
        """Lower the estimate by the tokens ``characters`` removed characters cost."""
        self.tokens -= characters * self.tokens_per_character


class ContextBudgetTrimmer:
    """Trims one agent's history once its estimated input exceeds ``token_threshold``."""

    def __init__(self, agent_id: str, token_threshold: int, thinking_in_requests: bool) -> None:
        self._agent_id = agent_id
        self._token_threshold = token_threshold
        # Reasoning that is never sent back costs the request nothing, so it is
        # priced at zero and stripping it is not a way to get under budget.
        self._thinking_in_requests = thinking_in_requests
        # Server usage describes the history as it was when that response was
        # generated. Tokens trimmed since then are remembered against the
        # response, so trimming again before a new response (a retried request)
        # does not re-read the stale count and trim further.
        self._usage_response: ModelResponse | None = None
        self._tokens_removed_since_usage = 0.0

    def trim(self, messages: list[ModelMessage]) -> list[ModelMessage]:
        """Return ``messages`` unchanged when under budget, otherwise a trimmed copy."""
        count_thinking = self._thinking_in_requests
        estimate = _estimate_input_tokens(messages=messages, count_thinking=count_thinking)
        usage_response = _latest_usage_response(messages=messages)
        if usage_response is not self._usage_response:
            self._usage_response = usage_response
            self._tokens_removed_since_usage = 0.0
        estimate.tokens -= self._tokens_removed_since_usage
        if estimate.tokens <= self._token_threshold:
            return messages
        before = estimate.tokens
        trimmed = messages
        if count_thinking:
            trimmed = _strip_old_thinking(messages=messages, estimate=estimate)
        if estimate.tokens > self._token_threshold:
            trimmed = _trim_old_tool_results(
                messages=trimmed,
                estimate=estimate,
                token_threshold=self._token_threshold,
                count_thinking=count_thinking,
            )
        self._tokens_removed_since_usage += before - estimate.tokens
        logger.info(
            "Agent %s history trimmed to fit context budget: ~%d -> ~%d tokens (threshold %d)",
            self._agent_id,
            before,
            estimate.tokens,
            self._token_threshold,
        )
        if estimate.tokens > self._token_threshold:
            logger.warning(
                "Agent %s history still exceeds the context budget after trimming "
                "(~%d tokens, threshold %d)",
                self._agent_id,
                estimate.tokens,
                self._token_threshold,
            )
        return trimmed


def _part_characters(part: Any, count_thinking: bool) -> int:
    """Characters a message part contributes to the rendered prompt.

    Reasoning counts only when it is sent back to the model.
    """
    if isinstance(part, ThinkingPart):
        if count_thinking:
            return len(part.content)
        return 0
    if isinstance(part, TextPart):
        return len(part.content)
    if isinstance(part, ToolCallPart):
        return len(part.args_as_json_str())
    if isinstance(part, ToolReturnPart):
        return len(part.model_response_str())
    content = getattr(part, "content", None)
    if isinstance(content, str):
        return len(content)
    return 0


def _message_characters(messages: list[ModelMessage], count_thinking: bool) -> int:
    """Total characters across every part of ``messages``."""
    return sum(
        _part_characters(part=part, count_thinking=count_thinking)
        for message in messages
        for part in message.parts
    )


def _has_usage(message: ModelMessage) -> bool:
    """True for a response carrying server-reported input tokens."""
    return isinstance(message, ModelResponse) and message.usage.input_tokens > 0


def _latest_usage_response(messages: list[ModelMessage]) -> ModelResponse | None:
    """The most recent response carrying server-reported usage, if any."""
    for message in reversed(messages):
        if isinstance(message, ModelResponse) and _has_usage(message=message):
            return message
    return None


def _estimate_input_tokens(messages: list[ModelMessage], count_thinking: bool) -> _TokenEstimate:
    """Estimate the next request's input tokens from the latest server-reported usage.

    The last response's input plus output tokens is exact for the history up to
    and including that response, as it stood then; messages after it are priced
    at the ratio that usage implies. With no usage yet, every character is priced
    at a fixed ratio.
    """
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, ModelResponse) or not _has_usage(message=message):
            continue
        reported = message.usage.input_tokens + message.usage.output_tokens
        covered_characters = _message_characters(
            messages=messages[: index + 1], count_thinking=count_thinking
        )
        ratio = FALLBACK_TOKENS_PER_CHARACTER
        if covered_characters > 0:
            ratio = min(
                max(reported / covered_characters, MIN_TOKENS_PER_CHARACTER),
                MAX_TOKENS_PER_CHARACTER,
            )
        tail_characters = _message_characters(
            messages=messages[index + 1 :], count_thinking=count_thinking
        )
        return _TokenEstimate(
            tokens=reported + tail_characters * ratio,
            tokens_per_character=ratio,
        )
    return _TokenEstimate(
        tokens=_message_characters(messages=messages, count_thinking=count_thinking)
        * FALLBACK_TOKENS_PER_CHARACTER,
        tokens_per_character=FALLBACK_TOKENS_PER_CHARACTER,
    )


def _strip_old_thinking(
    messages: list[ModelMessage],
    estimate: _TokenEstimate,
) -> list[ModelMessage]:
    """Drop reasoning from every response except the latest one."""
    last_response_index = -1
    for index, message in enumerate(messages):
        if isinstance(message, ModelResponse):
            last_response_index = index
    result: list[ModelMessage] = []
    for index, message in enumerate(messages):
        if not isinstance(message, ModelResponse) or index == last_response_index:
            result.append(message)
            continue
        kept = [part for part in message.parts if not isinstance(part, ThinkingPart)]
        if len(kept) == len(message.parts) or not kept:
            # Nothing to strip, or stripping would leave an empty response.
            result.append(message)
            continue
        estimate.subtract_characters(
            characters=sum(
                _part_characters(part=part, count_thinking=True)
                for part in message.parts
                if isinstance(part, ThinkingPart)
            )
        )
        result.append(replace(message, parts=kept))
    return result


def _is_pinned_tool_return(part: ToolReturnPart, superseded: set[str]) -> bool:
    """True for lifecycle notifications, which carry the agent's task card.

    A notification whose exact content is delivered again later in the history
    (a re-sent briefing) is pinned only in its latest copy.
    """
    if notification_type_of(part=part) not in _PINNED_NOTIFICATION_TYPES:
        return False
    return part.tool_call_id not in superseded


def _superseded_notification_call_ids(messages: list[ModelMessage]) -> set[str]:
    """Call ids of lifecycle notifications whose content recurs in a later tool return."""
    seen: set[str] = set()
    superseded: set[str] = set()
    for message in reversed(messages):
        if not isinstance(message, ModelRequest):
            continue
        for part in message.parts:
            if not isinstance(part, ToolReturnPart):
                continue
            if notification_type_of(part=part) not in _PINNED_NOTIFICATION_TYPES:
                continue
            key = _notification_identity(part=part)
            if key in seen:
                superseded.add(part.tool_call_id)
            seen.add(key)
    return superseded


def _notification_identity(part: ToolReturnPart) -> str:
    """The notification a return delivers, ignoring per-delivery queue counters."""
    content = part.content
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return part.model_response_str()
    if isinstance(content, dict):
        payload = {
            key: value
            for key, value in cast(dict[str, Any], content).items()
            if key not in ("pending_count", "current_round")
        }
        return json.dumps(payload, sort_keys=True, default=str)
    return part.model_response_str()


def _delivered_message_lines(content: object) -> list[str]:
    """Public message bodies a tool result delivered, rendered as text.

    Covers the rendered block that workspace results end with (including a
    string field inside a JSON result, such as a wake package's ``workspace``)
    and the ``new_messages`` list a ``send_message`` result returns.
    """
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            block = public_message_block(text=content)
            if block is None:
                return []
            return [block]
        if isinstance(parsed, (dict, list)):
            return _delivered_message_lines(content=cast(object, parsed))
        return []
    lines: list[str] = []
    if isinstance(content, dict):
        mapping = cast(dict[str, Any], content)
        new_messages = mapping.get("new_messages")
        if isinstance(new_messages, list) and new_messages:
            lines.append(PUBLIC_MESSAGES_HEADER)
            for entry in cast(list[Any], new_messages):
                if isinstance(entry, dict):
                    item = cast(dict[str, Any], entry)
                    lines.append(
                        f"[round {item.get('round')}; {item.get('sender')}] {item.get('text')}"
                    )
        for key, value in mapping.items():
            if key != "new_messages":
                lines.extend(_delivered_message_lines(content=value))
    elif isinstance(content, list):
        for value in cast(list[Any], content):
            lines.extend(_delivered_message_lines(content=value))
    return lines


def _trimmed_content(part: ToolReturnPart) -> str:
    """The placeholder that replaces a trimmed result, keeping its public messages."""
    lines = _delivered_message_lines(content=part.content)
    if not lines:
        return TRIMMED_TOOL_RESULT
    return "\n".join([f"{TRIMMED_TOOL_RESULT} {KEPT_MESSAGES_NOTE}", *lines])


def _is_trimmed(part: ToolReturnPart) -> bool:
    """True for a result this trimmer has already replaced."""
    return isinstance(part.content, str) and part.content.startswith(TRIMMED_TOOL_RESULT)


def _trim_old_tool_results(
    messages: list[ModelMessage],
    estimate: _TokenEstimate,
    token_threshold: int,
    count_thinking: bool,
) -> list[ModelMessage]:
    """Replace old tool-result content with a placeholder, oldest first, until under budget.

    Public message bodies are delivered once, inside the result that carried
    them, so the placeholder keeps them. The rest of the result (depot
    snapshots, receipts) is repeated in newer observations and is dropped.
    """
    cutoff = max(len(messages) - RECENT_MESSAGES_KEPT, 0)
    superseded = _superseded_notification_call_ids(messages=messages)
    result = list(messages)
    for index in range(cutoff):
        if estimate.tokens <= token_threshold:
            break
        message = result[index]
        if not isinstance(message, ModelRequest):
            continue
        new_parts: list[Any] = []
        changed = False
        for part in message.parts:
            if (
                isinstance(part, ToolReturnPart)
                and not _is_trimmed(part=part)
                and not _is_pinned_tool_return(part=part, superseded=superseded)
            ):
                replacement = _trimmed_content(part=part)
                estimate.subtract_characters(
                    characters=_part_characters(part=part, count_thinking=count_thinking)
                    - len(replacement)
                )
                new_parts.append(replace(part, content=replacement))
                changed = True
            else:
                new_parts.append(part)
        if changed:
            result[index] = replace(message, parts=new_parts)
    return result
