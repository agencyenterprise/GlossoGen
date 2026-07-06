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

import json
import logging
from datetime import datetime, timezone
from typing import Any, NamedTuple, cast

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

from schmidt.elapsed_time import elapsed_seconds_since_start, find_simulation_start_time
from schmidt.models.event import (
    LLMResponseReceived,
    SimulationEvent,
    ToolCallInvoked,
    ToolResultReceived,
)
from schmidt.models.tool_definition import ToolCallRequest
from schmidt.runners.communication_protocol import CONTINUE_PROMPT, INITIAL_PROMPT
from schmidt.runtime.scheduled_events import (
    ChannelVisibility,
    ChannelVisibilityFromRound,
    ChannelVisibilityNone,
)

logger = logging.getLogger(__name__)


CHANNEL_SCOPED_TOOLS: frozenset[str] = frozenset({"send_message", "read_channel"})


class _KeptCycle(NamedTuple):
    """One LLM cycle that survived cutoff filtering, ready to emit as messages."""

    response_timestamp: datetime
    stop_reason: str
    response_parts: list[ThinkingPart | TextPart | ToolCallPart]
    tool_return_parts: list[ToolReturnPart]
    parent_past_cutoff: bool


def _tool_call_filtered_by_visibility(
    tool_call: ToolCallRequest,
    invoked: ToolCallInvoked | None,
    channel_visibility: dict[str, ChannelVisibility],
) -> bool:
    """Return True when the tool call should be dropped per the channel-visibility config.

    Channels not present in ``channel_visibility`` default to ``Full``
    (keep). For channels that are present:
    - ``ChannelVisibilityNone`` drops the call entirely.
    - ``ChannelVisibilityFromRound(R)`` drops every ``read_channel`` call
      (its tool-return blob would leak older messages) and drops every
      ``send_message`` call whose ``ToolCallInvoked.round_number < R``.
      A missing ``ToolCallInvoked`` is treated as past-window so the
      call is dropped — defensive against malformed logs.
    """
    if tool_call.tool_name not in CHANNEL_SCOPED_TOOLS:
        return False
    channel_id = tool_call.arguments.get("channel_id")
    if not isinstance(channel_id, str):
        return False
    visibility = channel_visibility.get(channel_id)
    if visibility is None:
        return False
    if isinstance(visibility, ChannelVisibilityNone):
        return True
    if isinstance(visibility, ChannelVisibilityFromRound):
        if tool_call.tool_name == "read_channel":
            return True
        if invoked is None:
            return True
        return invoked.round_number < visibility.round_floor
    return False


def _derive_nonchannel_round_floor(
    channel_visibility: dict[str, ChannelVisibility],
) -> int | None:
    """Return the lowest round below which non-channel tool calls should be dropped.

    Channel-scoped tools (``send_message`` / ``read_channel``) are windowed
    per channel by ``_tool_call_filtered_by_visibility``. Non-channel tools
    are not, and would otherwise leak prior-round state the swap meant to
    hide: ``read_notifications`` returns carry the round-start injection text
    (e.g. ``--- PREVIOUS VEYRU RESULT ---``), and ``stabilize_veyru`` calls
    and returns reveal the agent's own prior actions, symptoms, and outcomes.
    The floor is the minimum ``round_floor`` across every
    ``ChannelVisibilityFromRound`` entry; non-channel calls before that round
    are dropped. Returns ``None`` (no filtering) when no channel uses
    ``FromRound`` — fork/resume flows pass ``Full`` visibility and keep the
    full history intact.
    """
    floors = [
        visibility.round_floor
        for visibility in channel_visibility.values()
        if isinstance(visibility, ChannelVisibilityFromRound)
    ]
    if not floors:
        return None
    return min(floors)


def _nonchannel_call_below_floor(
    tool_call: ToolCallRequest,
    invoked: ToolCallInvoked | None,
    nonchannel_round_floor: int | None,
) -> bool:
    """Return True when a non-channel tool call falls below the round floor.

    Applies to every tool that is not channel-scoped (e.g.
    ``read_notifications``, ``stabilize_veyru``); channel-scoped tools are
    windowed by ``_tool_call_filtered_by_visibility`` instead. Returns False
    when ``nonchannel_round_floor`` is ``None`` (no windowing) or for a
    channel-scoped tool. A missing ``ToolCallInvoked`` is treated as
    past-window so the call is dropped — defensive against malformed logs.
    """
    if nonchannel_round_floor is None:
        return False
    if tool_call.tool_name in CHANNEL_SCOPED_TOOLS:
        return False
    if invoked is None:
        return True
    return invoked.round_number < nonchannel_round_floor


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


def _read_channel_content_as_elapsed(
    content: str,
    simulation_start_time: datetime,
) -> str:
    """Rewrite a read_channel result's message times to elapsed seconds.

    Older JSONL logs stored each message with an ISO ``timestamp``; convert
    those to the ``elapsed_seconds`` float that agents now receive. Results
    already in the new format (or unparseable) are returned unchanged, so this
    is safe and idempotent across log generations.
    """
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content
    if not isinstance(payload, dict):
        return content
    payload_dict = cast(dict[str, Any], payload)
    raw_messages = payload_dict.get("messages")
    if not isinstance(raw_messages, list):
        return content
    messages = cast(list[Any], raw_messages)
    converted = False
    for entry in messages:
        if not isinstance(entry, dict):
            continue
        message = cast(dict[str, Any], entry)
        iso_timestamp = message.get("timestamp")
        if not isinstance(iso_timestamp, str):
            continue
        del message["timestamp"]
        message["elapsed_seconds"] = elapsed_seconds_since_start(
            when=datetime.fromisoformat(iso_timestamp),
            start=simulation_start_time,
        )
        converted = True
    if not converted:
        return content
    return json.dumps(payload_dict)


def _tool_return_content(
    result: ToolResultReceived,
    simulation_start_time: datetime,
) -> str:
    """Return a tool result's content, converting read_channel times to elapsed seconds."""
    if result.tool_name.endswith("read_channel"):
        return _read_channel_content_as_elapsed(
            content=result.result,
            simulation_start_time=simulation_start_time,
        )
    return result.result


def _build_orphan_cycle(
    orphan_invoked: list[ToolCallInvoked],
    tool_results_by_call_id: dict[str, ToolResultReceived],
    channel_visibility: dict[str, ChannelVisibility],
    nonchannel_round_floor: int | None,
    simulation_start_time: datetime,
) -> _KeptCycle | None:
    """Synthesise a ``_KeptCycle`` for ``ToolCallInvoked`` events with no parent.

    When an LLM cycle straddles the rewind anchor, its
    ``LLMResponseReceived`` is logged after the anchor and is not in
    the rewritten JSONL — but the individual ``ToolCallInvoked`` events
    that fired before the anchor *are* preserved (they were committed
    via subsequent committable events). Without their parent we'd lose
    the matching ``ToolCallPart``s entirely; instead we group them into
    one synthetic ``ModelResponse`` placed at the end of the agent's
    history (they are the most recent calls before resume). The
    channel-visibility filter still applies, and ``stop_reason`` is set
    to ``end_turn`` so the cycle is treated as terminal — the resumed
    agent picks up on a fresh prompt rather than a mid-batch continuation.
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
        if _tool_call_filtered_by_visibility(
            tool_call=request,
            invoked=inv,
            channel_visibility=channel_visibility,
        ):
            continue
        if _nonchannel_call_below_floor(
            tool_call=request,
            invoked=inv,
            nonchannel_round_floor=nonchannel_round_floor,
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
                content=_tool_return_content(
                    result=result,
                    simulation_start_time=simulation_start_time,
                ),
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


def _cycle_to_messages(
    cycle: _KeptCycle,
    split_parallel_tool_calls: bool,
) -> list[ModelMessage]:
    """Render one kept cycle into ``ModelResponse``/``ModelRequest`` messages.

    Normally one ``ModelResponse`` (all tool calls) followed by one
    ``ModelRequest`` (all tool returns). When ``split_parallel_tool_calls``
    is True and the cycle holds more than one tool call, the calls are
    serialized into one single-call ``ModelResponse`` plus its matching
    single-return ``ModelRequest`` per call. vLLM's tool parsers (llama3_json,
    hermes) reject any request whose history contains a turn with more than
    one tool call, so self-hosted agents resumed onto a frontier model's
    parallel-tool-call history need the history flattened to one call per
    turn. Leading thinking/text parts attach to the first emitted response.
    """
    tool_call_parts = [part for part in cycle.response_parts if isinstance(part, ToolCallPart)]
    if not split_parallel_tool_calls or len(tool_call_parts) <= 1:
        messages: list[ModelMessage] = [
            ModelResponse(parts=cycle.response_parts, timestamp=cycle.response_timestamp)
        ]
        if cycle.tool_return_parts:
            messages.append(ModelRequest(parts=cycle.tool_return_parts))
        return messages

    leading_parts = [part for part in cycle.response_parts if not isinstance(part, ToolCallPart)]
    returns_by_id = {ret.tool_call_id: ret for ret in cycle.tool_return_parts}
    messages = []
    for position, call_part in enumerate(tool_call_parts):
        if position == 0:
            response_parts: list[ThinkingPart | TextPart | ToolCallPart] = [
                *leading_parts,
                call_part,
            ]
        else:
            response_parts = [call_part]
        messages.append(ModelResponse(parts=response_parts, timestamp=cycle.response_timestamp))
        matching_return = returns_by_id.get(call_part.tool_call_id)
        if matching_return is not None:
            messages.append(ModelRequest(parts=[matching_return]))
    return messages


def resolve_history_timestamp(events: list[SimulationEvent]) -> datetime:
    """Pick a ``target_timestamp`` for ``build_message_history`` that keeps every event.

    When ``cutoff_round`` is set, ``target_timestamp`` is ignored. When it is
    ``None`` (end-of-run reconstruction), ``target_timestamp`` is the latest
    event's timestamp so no calls are dropped by timestamp filtering.
    """
    if not events:
        return datetime.now(tz=timezone.utc)
    return events[-1].timestamp


def build_message_history(
    events: list[SimulationEvent],
    agent_id: str,
    system_prompt: str,
    target_timestamp: datetime,
    cutoff_round: int | None,
    tool_calls_only: bool,
    channel_visibility: dict[str, ChannelVisibility],
    split_parallel_tool_calls: bool,
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

    Cutoff is **exclusive**: ``cutoff_round=R`` covers rounds
    ``1..R-1``. To capture state at the END of round R (e.g. the last
    activity of a phase that ended at round R), pass
    ``cutoff_round=R+1``.

    When ``tool_calls_only`` is True, ``TextPart`` and ``ThinkingPart``
    are stripped from each ``ModelResponse``; only ``ToolCallPart``
    instances survive. When ``tool_calls_only`` is False, text and
    thinking are also stripped from any parent response that itself
    falls past the cutoff (its verbal output reflected post-cutoff
    state). ``channel_visibility`` filters tool calls per channel —
    ``Full`` keeps everything (the default for channels not listed),
    ``None`` drops every send/read on the channel, and
    ``FromRound(R)`` drops every read and drops sends from rounds <R.
    Used by the replace-agent flow to hide e.g. postmortem traffic from
    the new agent while exposing recent protocol activity.

    When ``split_parallel_tool_calls`` is True, any reconstructed turn
    holding more than one tool call is serialized into one single-call
    response per call (see ``_cycle_to_messages``). Set it for self-hosted
    (vLLM) agents, whose tool parsers reject multi-tool-call turns in the
    request history; leave it False for Anthropic/OpenAI, which accept them.
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

    simulation_start_time = find_simulation_start_time(events=events)
    nonchannel_round_floor = _derive_nonchannel_round_floor(
        channel_visibility=channel_visibility,
    )

    kept_cycles: list[_KeptCycle] = []
    for llm_resp in llm_responses:
        kept_tool_calls: list[ToolCallRequest] = []
        for tc in llm_resp.tool_calls:
            if _tool_call_filtered_by_visibility(
                tool_call=tc,
                invoked=invoked_by_id.get(tc.call_id),
                channel_visibility=channel_visibility,
            ):
                continue
            if _nonchannel_call_below_floor(
                tool_call=tc,
                invoked=invoked_by_id.get(tc.call_id),
                nonchannel_round_floor=nonchannel_round_floor,
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
                        content=_tool_return_content(
                            result=result_event,
                            simulation_start_time=simulation_start_time,
                        ),
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
        channel_visibility=channel_visibility,
        nonchannel_round_floor=nonchannel_round_floor,
        simulation_start_time=simulation_start_time,
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
        messages.extend(
            _cycle_to_messages(
                cycle=cycle,
                split_parallel_tool_calls=split_parallel_tool_calls,
            )
        )
        is_last = index == len(kept_cycles) - 1
        if cycle.stop_reason == "end_turn" and not cycle.parent_past_cutoff and not is_last:
            messages.append(ModelRequest(parts=[UserPromptPart(content=CONTINUE_PROMPT)]))

    return messages
