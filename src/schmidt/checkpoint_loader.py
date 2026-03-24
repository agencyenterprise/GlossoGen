"""Loads and reconstructs simulation state from a JSONL event log for resume.

Parses the event log to find the last checkpoint, then extracts all channel
messages, notebook entries, and shared document edits up to that checkpoint.
Returns a ``ResumeState`` containing everything needed to continue the
simulation from where it left off.
"""

import logging
from typing import Any, NamedTuple

from schmidt.models.event import (
    CheckpointSaved,
    MessageSent,
    NotebookEntryWritten,
    SharedDocumentEdited,
    SimulationEvent,
)
from schmidt.models.message import SimulationMessage
from schmidt.tools.notebook_store import NotebookEntry

logger = logging.getLogger(__name__)


class ResumeState(NamedTuple):
    """All state needed to resume a simulation from its last checkpoint."""

    turn_number: int
    round_number: int
    last_turn_passed: bool
    scenario_checkpoint: dict[str, Any]
    last_injected_rounds: dict[str, int]
    messages_by_channel: dict[str, list[SimulationMessage]]
    notebook_entries: dict[str, list[NotebookEntry]]
    shared_document_contents: dict[str, str]


def build_resume_state(events: list[SimulationEvent]) -> ResumeState:
    """Find the last checkpoint in the event log and reconstruct all state up to it.

    Raises ``ValueError`` if no ``CheckpointSaved`` event is found in the log.
    """
    checkpoint = _find_last_checkpoint(events=events)
    checkpoint_ts = checkpoint.timestamp

    messages_by_channel: dict[str, list[SimulationMessage]] = {}
    notebook_entries: dict[str, list[NotebookEntry]] = {}
    shared_document_contents: dict[str, str] = {}

    for event in events:
        if event.timestamp > checkpoint_ts:
            break

        if isinstance(event, MessageSent):
            channel_id = event.message.channel_id
            if channel_id not in messages_by_channel:
                messages_by_channel[channel_id] = []
            messages_by_channel[channel_id].append(event.message)

        elif isinstance(event, NotebookEntryWritten):
            if event.agent_id not in notebook_entries:
                notebook_entries[event.agent_id] = []
            notebook_entries[event.agent_id].append(
                NotebookEntry(
                    round_number=event.round_number,
                    timestamp=event.timestamp,
                    text=event.entry_text,
                )
            )

        elif isinstance(event, SharedDocumentEdited):
            shared_document_contents[event.document_id] = event.content

    logger.info(
        "Resume state built: turn=%d, round=%d, channels=%d, notebooks=%d, docs=%d",
        checkpoint.turn_number,
        checkpoint.round_number,
        len(messages_by_channel),
        len(notebook_entries),
        len(shared_document_contents),
    )

    return ResumeState(
        turn_number=checkpoint.turn_number,
        round_number=checkpoint.round_number,
        last_turn_passed=checkpoint.last_turn_passed,
        scenario_checkpoint=checkpoint.scenario_state,
        last_injected_rounds=checkpoint.last_injected_rounds,
        messages_by_channel=messages_by_channel,
        notebook_entries=notebook_entries,
        shared_document_contents=shared_document_contents,
    )


def _find_last_checkpoint(events: list[SimulationEvent]) -> CheckpointSaved:
    """Return the last CheckpointSaved event from the log.

    Raises ``ValueError`` if no checkpoint exists.
    """
    last_checkpoint: CheckpointSaved | None = None
    for event in events:
        if isinstance(event, CheckpointSaved):
            last_checkpoint = event

    if last_checkpoint is None:
        raise ValueError(
            "No CheckpointSaved event found in the log. "
            "Cannot resume a simulation that has no checkpoints."
        )
    return last_checkpoint
