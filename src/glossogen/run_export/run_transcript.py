"""One run's event log as plain text, grouped by round, for a person or an agent to read.

The transcript keeps what each agent was told, wrote, called and received, in log
order. It leaves out what only the platform reads: event ids, timestamps, token
usage and token ids, wait and wake records, and the tool-call lines that repeat the
calls of a model response. An event that has no rule here, a scenario's own events
included, is printed with its fields as JSON.
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


def render_run_transcript(events: list[SimulationEvent]) -> list[TranscriptSection]:
    """Render ``events`` as one text section per round, in round order."""
    lines_by_round: dict[int, list[str]] = {}
    answered_call_ids: set[str] = set()
    for event in events:
        if isinstance(event, LLMResponseReceived):
            answered_call_ids.update(call.call_id for call in event.tool_calls)
        rendered = _render_event(event=event, answered_call_ids=answered_call_ids)
        if rendered is None:
            continue
        lines_by_round.setdefault(event.round_number, []).append(rendered)
    return [
        TranscriptSection(round_number=round_number, text="\n".join(lines))
        for round_number, lines in sorted(lines_by_round.items())
    ]


def section_heading(round_number: int) -> str:
    """The heading line printed above a section."""
    if round_number == 0:
        return "=== Before round 1 ==="
    return f"=== Round {round_number} ==="


def _render_event(event: SimulationEvent, answered_call_ids: set[str]) -> str | None:
    """One event as text, or None for an event the transcript leaves out."""
    if isinstance(event, AgentResumed):
        return None
    if isinstance(event, ToolCallInvoked) and event.call_id in answered_call_ids:
        return None
    if isinstance(event, WaitRegistered):
        return _render_wait(event=event)
    if isinstance(event, SimulationStarted):
        return _render_simulation_started(event=event)
    if isinstance(event, AgentRegistered):
        return _render_agent_registered(event=event)
    if isinstance(event, LLMResponseReceived):
        return _render_llm_response(event=event)
    if isinstance(event, ToolCallInvoked):
        return f"[{event.agent_id} calls] {event.tool_name}({_to_json(value=event.arguments)})"
    if isinstance(event, ToolResultReceived):
        return f"[{event.agent_id} receives from {event.tool_name}] {event.result}"
    if isinstance(event, MessageSent):
        message = event.message
        return f"[{message.sender_agent_id} -> #{message.channel_id}] {message.text}"
    if isinstance(event, InjectionDelivered):
        return f"[briefing to {event.agent_id}]\n{event.text}"
    return _render_other(event=event)


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


def _render_llm_response(event: LLMResponseReceived) -> str:
    """A model response: its reasoning, its text and the tool calls that it made."""
    parts: list[str] = []
    if event.thinking:
        parts.append(f"[{event.agent_id} thinks]\n{event.thinking}")
    if event.text:
        parts.append(f"[{event.agent_id} writes]\n{event.text}")
    for call in event.tool_calls:
        parts.append(f"[{event.agent_id} calls] {call.tool_name}({_to_json(value=call.arguments)})")
    if not parts:
        return f"[{event.agent_id}] empty response, stop reason {event.stop_reason}"
    return "\n".join(parts)


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
