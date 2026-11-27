"""One run's event log as plain text, grouped by round, for a person or an agent to read.

The transcript keeps what each agent was told, wrote, called and received. It leaves
out what only the platform reads: event ids, timestamps, token usage and token ids,
and wait and wake records. An event that has no rule here, a scenario's own events
included, is printed with its fields as JSON.

Events print in log order with one exception. The log records a model response after
the tool calls that it made have run. So a response's reasoning and text print just
before its first call, and each call prints once, from its ``tool_call_invoked`` event.
"""

import json
from typing import Any, NamedTuple

from glossogen.models.event import (
    AgentRegistered,
    AgentResumed,
    InjectionDelivered,
    LLMResponseReceived,
    MessageSent,
    SimulationEvent,
    SimulationStarted,
    ToolCallInvoked,
    ToolResultReceived,
    UnrecognizedEvent,
    WaitRegistered,
)
from glossogen.models.glossogen_build import GlossogenBuild

_PLATFORM_ONLY_FIELDS = frozenset({"event_id", "timestamp", "event_type", "round_number", "usage"})


class TranscriptSection(NamedTuple):
    """The rendered events of one round; round 0 holds what the log records before round 1."""

    round_number: int
    text: str


class _ResponseIndex(NamedTuple):
    """The tool calls that ran, and the model response that made each of them."""

    invoked_call_ids: frozenset[str]
    response_by_call_id: dict[str, LLMResponseReceived]


def render_run_transcript(events: list[SimulationEvent]) -> list[TranscriptSection]:
    """Render ``events`` as one text section per round, in round order."""
    index = _index_responses(events=events)
    shown_response_ids: set[str] = set()
    lines_by_round: dict[int, list[str]] = {}
    for event in events:
        for line in _render_event(event=event, index=index, shown_response_ids=shown_response_ids):
            lines_by_round.setdefault(event.round_number, []).append(line)
    return [
        TranscriptSection(round_number=round_number, text="\n".join(lines))
        for round_number, lines in sorted(lines_by_round.items())
    ]


def section_heading(round_number: int) -> str:
    """The heading line printed above a section."""
    if round_number == 0:
        return "=== Before round 1 ==="
    return f"=== Round {round_number} ==="


def _index_responses(events: list[SimulationEvent]) -> _ResponseIndex:
    """Find which tool calls ran, and which response made each call that ran."""
    invoked_call_ids = frozenset(
        event.call_id for event in events if isinstance(event, ToolCallInvoked)
    )
    response_by_call_id = {
        call.call_id: event
        for event in events
        if isinstance(event, LLMResponseReceived)
        for call in event.tool_calls
        if call.call_id in invoked_call_ids
    }
    return _ResponseIndex(
        invoked_call_ids=invoked_call_ids, response_by_call_id=response_by_call_id
    )


def _render_event(
    event: SimulationEvent, index: _ResponseIndex, shown_response_ids: set[str]
) -> list[str]:
    """One event as lines of text; no lines for an event that the transcript leaves out."""
    if isinstance(event, ToolCallInvoked):
        return _render_tool_call(event=event, index=index, shown_response_ids=shown_response_ids)
    if isinstance(event, LLMResponseReceived):
        return _render_llm_response(event=event, index=index, shown_response_ids=shown_response_ids)
    rendered = _render_single(event=event)
    if rendered is None:
        return []
    return [rendered]


def _render_single(event: SimulationEvent) -> str | None:
    """An event that renders on its own, or None for an event the transcript leaves out."""
    if isinstance(event, AgentResumed):
        return None
    if isinstance(event, WaitRegistered):
        return _render_wait(event=event)
    if isinstance(event, SimulationStarted):
        return _render_simulation_started(event=event)
    if isinstance(event, AgentRegistered):
        return _render_agent_registered(event=event)
    if isinstance(event, ToolResultReceived):
        return f"[{event.agent_id} receives from {event.tool_name}] {event.result}"
    if isinstance(event, MessageSent):
        message = event.message
        return f"[{message.sender_agent_id} -> #{message.channel_id}] {message.readable_text}"
    if isinstance(event, InjectionDelivered):
        return f"[briefing to {event.agent_id}]\n{event.text}"
    return _render_other(event=event)


def _render_tool_call(
    event: ToolCallInvoked, index: _ResponseIndex, shown_response_ids: set[str]
) -> list[str]:
    """A call that ran, after the reasoning and text of its response when not yet shown."""
    lines: list[str] = []
    response = index.response_by_call_id.get(event.call_id)
    if response is not None and response.event_id not in shown_response_ids:
        shown_response_ids.add(response.event_id)
        lines.extend(_response_words(response=response))
    lines.append(
        _call_line(agent_id=event.agent_id, tool_name=event.tool_name, arguments=event.arguments)
    )
    return lines


def _render_llm_response(
    event: LLMResponseReceived, index: _ResponseIndex, shown_response_ids: set[str]
) -> list[str]:
    """A response's reasoning and text when not yet shown, and the calls that never ran."""
    if not event.thinking and not event.text and not event.tool_calls:
        return [f"[{event.agent_id}] empty response, stop reason {event.stop_reason}"]
    lines: list[str] = []
    if event.event_id not in shown_response_ids:
        shown_response_ids.add(event.event_id)
        lines.extend(_response_words(response=event))
    lines.extend(
        _call_line(agent_id=event.agent_id, tool_name=call.tool_name, arguments=call.arguments)
        for call in event.tool_calls
        if call.call_id not in index.invoked_call_ids
    )
    return lines


def _response_words(response: LLMResponseReceived) -> list[str]:
    """A model response's reasoning and text."""
    words: list[str] = []
    if response.thinking:
        words.append(f"[{response.agent_id} thinks]\n{response.thinking}")
    if response.text:
        words.append(f"[{response.agent_id} writes]\n{response.text}")
    return words


def _call_line(agent_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
    """A tool call with its arguments."""
    return f"[{agent_id} calls] {tool_name}({_to_json(value=arguments)})"


def _render_wait(event: WaitRegistered) -> str | None:
    """A wait, shown only when the agent gave a reason for it."""
    if event.reasoning is None:
        return None
    return f"[{event.agent_id} waits for {event.wait_for.value}] {event.reasoning}"


def _render_simulation_started(event: SimulationStarted) -> str:
    """The run's identity, scenario, code version and recorded config."""
    return "\n".join(
        [
            f"Run: {event.run_id}",
            f"Scenario: {event.scenario_name}",
            f"Scenario description: {event.scenario_description}",
            f"glossogen: {_describe_build(build=event.glossogen_build)}",
            f"Provider: {event.provider}",
            f"Channels: {_list_or_none(items=event.channel_ids)}",
            f"Config: {_to_json(value=event.scenario_config)}",
        ]
    )


def _describe_build(build: GlossogenBuild | None) -> str:
    """The glossogen version and commit, or a note that the log does not record them."""
    if build is None:
        return "not recorded in this log"
    if build.git_commit is None:
        return f"{build.version}, commit not recorded"
    if build.has_uncommitted_changes:
        return f"{build.version}, commit {build.git_commit} with uncommitted changes in src/"
    return f"{build.version}, commit {build.git_commit}"


def _render_agent_registered(event: AgentRegistered) -> str:
    """An agent's seat, model, channels, tools and full system prompt."""
    return "\n".join(
        [
            f"[agent {event.agent_id} registers] role {event.role_name}, "
            f"model {event.model} on {event.provider}",
            f"Channels: {_list_or_none(items=event.channel_ids)}",
            f"Tools: {_list_or_none(items=event.tool_names)}",
            "System prompt:",
            event.system_prompt,
        ]
    )


def _render_other(event: SimulationEvent) -> str:
    """An event with no rule of its own: its type and its fields as JSON."""
    if isinstance(event, UnrecognizedEvent):
        record = event.payload
    else:
        record = event.model_dump(mode="json")
    fields = {key: value for key, value in record.items() if key not in _PLATFORM_ONLY_FIELDS}
    return f"[{record['event_type']}] {_to_json(value=fields)}"


def _list_or_none(items: list[str]) -> str:
    """Comma-separated items, or "none" for an empty list."""
    if not items:
        return "none"
    return ", ".join(items)


def _to_json(value: Any) -> str:
    """Compact JSON that keeps non-ASCII characters as they are."""
    return json.dumps(value, ensure_ascii=False)
