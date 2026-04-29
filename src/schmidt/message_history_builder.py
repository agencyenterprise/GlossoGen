"""Builds pydantic-ai ModelMessage history from simulation JSONL events.

Reconstructs the multi-turn conversation an agent experienced during a
simulation, producing a list of ``ModelMessage`` objects suitable for
passing as ``message_history`` to ``agent.run()`` on resume. Includes
thinking parts, text parts, tool calls, and tool results in the same
structure pydantic-ai produces during a live run.

Per-tool-call cutoff: a single ``LLMResponseReceived`` is logged at flush
time (when the LLM cycle ends), so a cycle that starts in round N-1 and
ends in round N is timestamped after the round-N rewind anchor and would
otherwise drop all of its tool calls — even ones executed in round N-1.
This module instead consults each tool call's own ``ToolCallInvoked``
event to filter individual calls, so pre-cutoff calls survive even when
their parent batch finished post-cutoff.
"""

import logging
from datetime import datetime
from typing import NamedTuple

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from schmidt.models.event import (
    LLMResponseReceived,
    SimulationEvent,
    ToolCallInvoked,
    ToolResultReceived,
)
from schmidt.models.tool_definition import ToolCallRequest
from schmidt.runners.communication_protocol import CONTINUE_PROMPT, INITIAL_PROMPT

logger = logging.getLogger(__name__)


CHANNEL_SCOPED_TOOLS: frozenset[str] = frozenset({"send_message", "read_channel"})


class _KeptCycle(NamedTuple):
    """One LLM cycle that survived cutoff filtering, ready to emit as messages."""

    response_timestamp: datetime
    stop_reason: str
    response_parts: list[ThinkingPart | TextPart | ToolCallPart]
    tool_return_parts: list[ToolReturnPart]
    parent_past_cutoff: bool


def _tool_call_targets_blocked_channel(
    tool_call: ToolCallRequest,
    blocked_channel_ids: frozenset[str],
) -> bool:
    """Return True when the tool call targets a channel in the blocked set."""
    if tool_call.tool_name not in CHANNEL_SCOPED_TOOLS:
        return False
    channel_id = tool_call.arguments.get("channel_id")
    return isinstance(channel_id, str) and channel_id in blocked_channel_ids


def _tool_call_at_or_past_cutoff(
    call_id: str,
    invoked_by_id: dict[str, ToolCallInvoked],
    cutoff_round: int | None,
    target_timestamp: datetime,
) -> bool:
    """Return True when the individual tool call falls at or past the cutoff.

    Looks up the call's own ``ToolCallInvoked`` event for its
    execution-time round and timestamp. When ``cutoff_round`` is set,
    filter by round (call.round_number >= cutoff_round drops the call).
    Otherwise filter by timestamp (call.timestamp > target_timestamp).
    A missing ``ToolCallInvoked`` is treated as past-cutoff so the call
    is dropped — defensive against malformed logs.
    """
    invoked = invoked_by_id.get(call_id)
    if invoked is None:
        return True
    if cutoff_round is not None:
        return invoked.round_number >= cutoff_round
    return invoked.timestamp > target_timestamp


def _drop_call_without_result(
    call_id: str,
    tool_results_by_call_id: dict[str, ToolResultReceived],
) -> bool:
    """Return True when the tool call has no preserved ``ToolResultReceived``.

    pydantic-ai requires every ``ToolCallPart`` in a ``ModelResponse``
    to have a matching ``ToolReturnPart`` in the next ``ModelRequest``;
    otherwise the model API rejects the request. A tool call invoked
    before the rewind anchor whose result was logged afterwards (the
    result event therefore not in the rewritten JSONL) must be dropped
    on both sides — keeping just the call would leave it dangling.
    """
    return call_id not in tool_results_by_call_id


def _build_orphan_cycle(
    orphan_invoked: list[ToolCallInvoked],
    tool_results_by_call_id: dict[str, ToolResultReceived],
    blocked_channel_ids: frozenset[str],
) -> "_KeptCycle | None":
    """Synthesise a ``_KeptCycle`` for ``ToolCallInvoked`` events with no parent.

    When an LLM cycle straddles the rewind anchor, its
    ``LLMResponseReceived`` is logged after the anchor and is not in
    the rewritten JSONL — but the individual ``ToolCallInvoked`` events
    that fired before the anchor *are* preserved (they were committed
    via subsequent committable events). Without their parent we'd lose
    the matching ``ToolCallPart``s entirely; instead we group them into
    one synthetic ``ModelResponse`` placed at the end of the agent's
    history (they are the most recent calls before resume). Blocked
    channels still apply, and ``stop_reason`` is set to ``end_turn``
    so the cycle is treated as terminal — the resumed agent picks up
    on a fresh prompt rather than a mid-batch continuation.
    """
    if not orphan_invoked:
        return None
    sorted_invoked = sorted(orphan_invoked, key=lambda inv: inv.timestamp)
    response_parts: list[ThinkingPart | TextPart | ToolCallPart] = []
    tool_return_parts: list[ToolReturnPart] = []
    for inv in sorted_invoked:
        request = ToolCallRequest(
            tool_name=inv.tool_name,
            arguments=inv.arguments,
            call_id=inv.call_id,
        )
        if _tool_call_targets_blocked_channel(
            tool_call=request,
            blocked_channel_ids=blocked_channel_ids,
        ):
            continue
        if _drop_call_without_result(
            call_id=inv.call_id,
            tool_results_by_call_id=tool_results_by_call_id,
        ):
            continue
        result = tool_results_by_call_id[inv.call_id]
        response_parts.append(
            ToolCallPart(
                tool_name=inv.tool_name,
                args=inv.arguments,
                tool_call_id=inv.call_id,
            )
        )
        tool_return_parts.append(
            ToolReturnPart(
                tool_name=result.tool_name,
                content=result.result,
                tool_call_id=result.call_id,
                timestamp=result.timestamp,
            )
        )
    if not response_parts:
        return None
    return _KeptCycle(
        response_timestamp=sorted_invoked[-1].timestamp,
        stop_reason="end_turn",
        response_parts=response_parts,
        tool_return_parts=tool_return_parts,
        parent_past_cutoff=True,
    )


def _llm_response_at_or_past_cutoff(
    llm_resp: LLMResponseReceived,
    cutoff_round: int | None,
    target_timestamp: datetime,
) -> bool:
    """Return True when the parent LLM response itself falls at or past the cutoff."""
    if cutoff_round is not None:
        return llm_resp.round_number >= cutoff_round
    return llm_resp.timestamp > target_timestamp


def build_message_history(
    events: list[SimulationEvent],
    agent_id: str,
    system_prompt: str,
    target_timestamp: datetime,
    cutoff_round: int | None,
    tool_calls_only: bool,
    blocked_channel_ids: frozenset[str],
) -> list[ModelMessage]:
    """Build a pydantic-ai message history for an agent from JSONL events.

    Walks events chronologically, extracting LLM responses and tool
    results for the specified agent up to the cutoff. Filtering is
    applied per individual tool call (via the matching
    ``ToolCallInvoked`` event), so calls executed before the cutoff
    survive even when their parent ``LLMResponseReceived`` was logged
    after it. When ``cutoff_round`` is set, individual calls are kept
    iff their ``ToolCallInvoked.round_number < cutoff_round``; when it
    is ``None``, the legacy ``ToolCallInvoked.timestamp <=
    target_timestamp`` predicate is used (fork / ``--resume`` flows).

    When ``tool_calls_only`` is True, ``TextPart`` and ``ThinkingPart``
    are stripped from each ``ModelResponse``; only ``ToolCallPart``
    instances survive. When ``tool_calls_only`` is False, text and
    thinking are also stripped from any parent response that itself
    falls past the cutoff (its verbal output reflected post-cutoff
    state). When ``blocked_channel_ids`` is non-empty, every
    ``send_message`` and ``read_channel`` call targeting one of those
    channels is dropped along with its matching tool return — used by
    the replace-agent flow to hide e.g. postmortem traffic from the
    new agent while exposing the rest of the prior tool history.
    """
    llm_responses: list[LLMResponseReceived] = []
    tool_results_by_call_id: dict[str, ToolResultReceived] = {}
    invoked_by_id: dict[str, ToolCallInvoked] = {}
    agent_invoked: list[ToolCallInvoked] = []

    for event in events:
        if isinstance(event, ToolCallInvoked):
            invoked_by_id[event.call_id] = event
            if event.agent_id == agent_id:
                agent_invoked.append(event)
        if isinstance(event, LLMResponseReceived) and event.agent_id == agent_id:
            llm_responses.append(event)
        elif isinstance(event, ToolResultReceived) and event.agent_id == agent_id:
            tool_results_by_call_id[event.call_id] = event

    parented_call_ids: set[str] = set()
    for llm_resp in llm_responses:
        for tc in llm_resp.tool_calls:
            parented_call_ids.add(tc.call_id)
    orphan_invoked: list[ToolCallInvoked] = [
        inv
        for inv in agent_invoked
        if inv.call_id not in parented_call_ids
        and not _tool_call_at_or_past_cutoff(
            call_id=inv.call_id,
            invoked_by_id=invoked_by_id,
            cutoff_round=cutoff_round,
            target_timestamp=target_timestamp,
        )
    ]

    if not llm_responses and not orphan_invoked:
        return []

    kept_cycles: list[_KeptCycle] = []
    for llm_resp in llm_responses:
        kept_tool_calls: list[ToolCallRequest] = []
        for tc in llm_resp.tool_calls:
            if _tool_call_targets_blocked_channel(
                tool_call=tc,
                blocked_channel_ids=blocked_channel_ids,
            ):
                continue
            if _tool_call_at_or_past_cutoff(
                call_id=tc.call_id,
                invoked_by_id=invoked_by_id,
                cutoff_round=cutoff_round,
                target_timestamp=target_timestamp,
            ):
                continue
            if _drop_call_without_result(
                call_id=tc.call_id,
                tool_results_by_call_id=tool_results_by_call_id,
            ):
                continue
            kept_tool_calls.append(tc)

        parent_past_cutoff = _llm_response_at_or_past_cutoff(
            llm_resp=llm_resp,
            cutoff_round=cutoff_round,
            target_timestamp=target_timestamp,
        )

        response_parts: list[ThinkingPart | TextPart | ToolCallPart] = []

        if not tool_calls_only and not parent_past_cutoff:
            thinking = getattr(llm_resp, "thinking", None)
            if thinking:
                response_parts.append(ThinkingPart(content=thinking))

            if llm_resp.text:
                response_parts.append(TextPart(content=llm_resp.text))

        for tc in kept_tool_calls:
            response_parts.append(
                ToolCallPart(
                    tool_name=tc.tool_name,
                    args=tc.arguments,
                    tool_call_id=tc.call_id,
                )
            )

        if not response_parts:
            continue

        tool_return_parts: list[ToolReturnPart] = []
        for tc in kept_tool_calls:
            result_event = tool_results_by_call_id.get(tc.call_id)
            if result_event is not None:
                tool_return_parts.append(
                    ToolReturnPart(
                        tool_name=result_event.tool_name,
                        content=result_event.result,
                        tool_call_id=result_event.call_id,
                        timestamp=result_event.timestamp,
                    )
                )

        kept_cycles.append(
            _KeptCycle(
                response_timestamp=llm_resp.timestamp,
                stop_reason=llm_resp.stop_reason,
                response_parts=response_parts,
                tool_return_parts=tool_return_parts,
                parent_past_cutoff=parent_past_cutoff,
            )
        )

    orphan_cycle = _build_orphan_cycle(
        orphan_invoked=orphan_invoked,
        tool_results_by_call_id=tool_results_by_call_id,
        blocked_channel_ids=blocked_channel_ids,
    )
    if orphan_cycle is not None:
        kept_cycles.append(orphan_cycle)

    if not kept_cycles:
        return []

    messages: list[ModelMessage] = [
        ModelRequest(
            parts=[
                SystemPromptPart(content=system_prompt),
                UserPromptPart(content=INITIAL_PROMPT),
            ],
        )
    ]

    for index, cycle in enumerate(kept_cycles):
        messages.append(
            ModelResponse(
                parts=cycle.response_parts,
                timestamp=cycle.response_timestamp,
            )
        )
        if cycle.tool_return_parts:
            messages.append(ModelRequest(parts=cycle.tool_return_parts))
        is_last = index == len(kept_cycles) - 1
        if cycle.stop_reason == "end_turn" and not cycle.parent_past_cutoff and not is_last:
            messages.append(ModelRequest(parts=[UserPromptPart(content=CONTINUE_PROMPT)]))

    return messages
