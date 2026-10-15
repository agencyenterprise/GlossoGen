"""The reasoning entries one ``LLMResponseReceived`` contributes to a run's detail.

A response can carry the model's own text, the reasoning its provider exposed,
or both. Each becomes its own entry, the thinking first, so a reasoning model
that writes no text (OpenAI's gpt-5 family answers with the tool call alone
and exposes a summary of its reasoning) still shows what it was doing.
"""

from glossogen.models.event import LLMResponseReceived
from glossogen.server.runs.models import ReasoningEntry, ReasoningKind

THINKING_ENTRY_SUFFIX = ":thinking"
"""Appended to the event id for the thinking entry, so the text entry keeps the id."""


def exposed_thinking(event: LLMResponseReceived) -> str:
    """The response's reasoning as display text, one part per paragraph; empty when none."""
    parts = [part.content.strip() for part in event.thinking_parts if part.content.strip()]
    if parts:
        return "\n\n".join(parts)
    if event.thinking is None:
        return ""
    return event.thinking.strip()


def reasoning_entries_of(event: LLMResponseReceived) -> list[ReasoningEntry]:
    """The entries ``event`` contributes: its thinking, then its text, each only when present."""
    entries: list[ReasoningEntry] = []
    thinking = exposed_thinking(event=event)
    if thinking:
        entries.append(
            ReasoningEntry(
                message_id=event.event_id + THINKING_ENTRY_SUFFIX,
                sender_agent_id=event.agent_id,
                kind=ReasoningKind.THINKING,
                text=thinking,
                timestamp=event.timestamp,
                round_number=event.round_number,
                channel_ids=[],
            )
        )
    if event.text is not None and event.text.strip():
        entries.append(
            ReasoningEntry(
                message_id=event.event_id,
                sender_agent_id=event.agent_id,
                kind=ReasoningKind.TEXT,
                text=event.text,
                timestamp=event.timestamp,
                round_number=event.round_number,
                channel_ids=[],
            )
        )
    return entries
