"""Persist each agent's reconstructed pydantic-ai message history at resume.

Whenever a run starts via ``--resume`` (plain resume, fork, or
replace-agent), the supervisor passes a reconstructed ``message_history``
to every agent's pydantic-ai ``Agent.run()`` call. That history is the
ground truth of what the model "remembers" about prior rounds — the
filtered tool calls, the surviving text/thinking parts, the injected
system and user prompts. None of that is captured in the JSONL event
log.

This module dumps the histories to ``resume_context_{agent_id}.json``
files inside the run directory before the simulation launches, so
later tools (FE, debugging scripts, evaluators) can introspect exactly
what the resumed agent saw on its first turn without re-running the
rewind builder.
"""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic_ai.messages import ModelMessage

logger = logging.getLogger(__name__)


def _serialize_part(part: object) -> dict[str, Any]:
    """Render a single ModelMessage part as a JSON-friendly dict.

    Falls back to ``{"kind": <classname>}`` for part types we do not
    explicitly handle, so a future pydantic-ai update introducing a new
    part variant degrades gracefully instead of raising.
    """
    cls = type(part).__name__
    if cls == "SystemPromptPart":
        return {"kind": "system", "content": getattr(part, "content", "")}
    if cls == "UserPromptPart":
        return {"kind": "user", "content": getattr(part, "content", "")}
    if cls == "TextPart":
        return {"kind": "text", "content": getattr(part, "content", "")}
    if cls == "ThinkingPart":
        return {"kind": "thinking", "content": getattr(part, "content", "")}
    if cls == "ToolCallPart":
        return {
            "kind": "tool_call",
            "tool_name": getattr(part, "tool_name", ""),
            "args": getattr(part, "args", None),
            "call_id": getattr(part, "tool_call_id", ""),
        }
    if cls == "ToolReturnPart":
        return {
            "kind": "tool_return",
            "tool_name": getattr(part, "tool_name", ""),
            "content": getattr(part, "content", ""),
            "call_id": getattr(part, "tool_call_id", ""),
        }
    return {"kind": cls}


def _serialize_message(message: ModelMessage) -> dict[str, Any]:
    """Render a ModelMessage (request or response) as a JSON-friendly dict."""
    return {
        "role": type(message).__name__,
        "parts": [_serialize_part(part=part) for part in message.parts],
    }


def write_resume_context_files(
    run_dir: Path,
    agent_message_histories: dict[str, list[ModelMessage]],
) -> None:
    """Write one JSON file per agent capturing its reconstructed history."""
    for agent_id, history in agent_message_histories.items():
        path = run_dir / f"resume_context_{agent_id}.json"
        payload = {
            "agent_id": agent_id,
            "num_messages": len(history),
            "messages": [_serialize_message(message=message) for message in history],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        logger.info(
            "Wrote resume context for %s: %d messages -> %s",
            agent_id,
            len(history),
            path.name,
        )


def write_swap_resume_context_file(
    run_dir: Path,
    agent_id: str,
    round_number: int,
    history: list[ModelMessage],
) -> None:
    """Dump a per-swap resume context for verification of in-run agent swaps.

    Distinct filename per swap (``resume_context_<agent_id>_round_<R>.json``)
    so multiple swaps in the same run do not overwrite each other. Used by
    the in-run scheduled-swap flow to make the new agent's seed history
    inspectable after the fact.
    """
    path = run_dir / f"resume_context_{agent_id}_round_{round_number}.json"
    payload = {
        "agent_id": agent_id,
        "round_number": round_number,
        "num_messages": len(history),
        "messages": [_serialize_message(message=message) for message in history],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    logger.info(
        "Wrote swap resume context for %s @ round %d: %d messages -> %s",
        agent_id,
        round_number,
        len(history),
        path.name,
    )
