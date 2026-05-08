"""Cached loader for the veyru protocol-probe question bank.

The bank lives at ``src/schmidt/scenarios/veyru/protocol_probe_questions.json``
and ships 28 entries (14 motifs × {observer, engineer}). Probe rows reference
each entry by ``question_id``; the streamlit probe-similarity tab uses this
loader to surface the question's *prompt* alongside the agent's response so
the reader does not have to cross-reference IDs in their head.

The module is streamlit-free.
"""

from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import orjson

_QUESTIONS_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "schmidt"
    / "scenarios"
    / "veyru"
    / "protocol_probe_questions.json"
)


class ProbeQuestionPrompt(NamedTuple):
    """Display-ready summary of one question-bank entry.

    ``display_text`` is a single-line human-readable rendering of the
    question's inputs (symptoms for observer questions, observer message
    + matched motif + canonical action for engineer questions).
    """

    question_id: str
    agent_role_filter: str
    display_text: str


def _format_display_text(agent_role_filter: str, inputs: dict[str, str]) -> str:
    """Render the bank-entry inputs as one human-readable line."""
    if agent_role_filter == "field_observer":
        symptoms = inputs.get("symptoms", "")
        return f"symptoms: {symptoms}"
    observer_message = inputs.get("observer_message", "")
    matched_motif = inputs.get("matched_motif", "")
    stellar_action_text = inputs.get("stellar_action_text", "")
    return (
        f"obs msg: {observer_message}  ·  motif: {matched_motif}  ·  "
        f"canon action: {stellar_action_text}"
    )


@lru_cache(maxsize=1)
def _load_question_bank() -> dict[str, ProbeQuestionPrompt]:
    """Read the bank from disk once per process and index by ``question_id``."""
    if not _QUESTIONS_PATH.exists():
        return {}
    raw = orjson.loads(_QUESTIONS_PATH.read_bytes())
    if not isinstance(raw, list):
        return {}
    out: dict[str, ProbeQuestionPrompt] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        question_id = entry.get("id")
        agent_role_filter = entry.get("agent_role_filter")
        inputs = entry.get("inputs")
        if not isinstance(question_id, str):
            continue
        if not isinstance(agent_role_filter, str):
            continue
        if not isinstance(inputs, dict):
            continue
        typed_inputs = {key: value for key, value in inputs.items() if isinstance(value, str)}
        out[question_id] = ProbeQuestionPrompt(
            question_id=question_id,
            agent_role_filter=agent_role_filter,
            display_text=_format_display_text(
                agent_role_filter=agent_role_filter, inputs=typed_inputs
            ),
        )
    return out


def get_question_prompt(question_id: str) -> ProbeQuestionPrompt:
    """Return the display-ready prompt for ``question_id``.

    Falls back to a placeholder entry when the bank file is unavailable
    or the id is unknown — this keeps the tab rendering even on an
    older run that references retired questions.
    """
    bank = _load_question_bank()
    found = bank.get(question_id)
    if found is not None:
        return found
    return ProbeQuestionPrompt(
        question_id=question_id,
        agent_role_filter="unknown",
        display_text="(prompt not found in current bank)",
    )
