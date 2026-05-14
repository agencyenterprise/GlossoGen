"""Cached loader for per-scenario protocol-probe question banks.

Each scenario that opts into the protocol-probe metric family ships a
``protocol_probe_questions.json`` file alongside its ``scenario.py``.
The probe-similarity tab uses this loader to surface a question's
prompt text alongside the agent's response so the reader does not have
to cross-reference IDs in their head.

The module is streamlit-free.
"""

from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import orjson


class ProbeQuestionPrompt(NamedTuple):
    """Display-ready summary of one question-bank entry.

    ``display_text`` renders the question's inputs as a single
    human-readable line. The rendering is keyed off
    ``agent_role_filter``; unknown filters fall through to a generic
    ``key=value`` join.
    """

    question_id: str
    agent_role_filter: str
    display_text: str


def _format_display_text(agent_role_filter: str, inputs: dict[str, str]) -> str:
    """Render the bank-entry inputs as one human-readable line.

    Falls back to a generic ``key=value`` summary when the filter is
    not one veyru's known shapes, so a new scenario's bank renders
    without requiring per-scenario formatting code.
    """
    if agent_role_filter == "field_observer":
        return f"symptoms: {inputs.get('symptoms', '')}"
    if agent_role_filter == "stabilization_engineer":
        observer_message = inputs.get("observer_message", "")
        matched_motif = inputs.get("matched_motif", "")
        stellar_action_text = inputs.get("stellar_action_text", "")
        return (
            f"obs msg: {observer_message}  ·  motif: {matched_motif}  ·  "
            f"canon action: {stellar_action_text}"
        )
    return "  ·  ".join(f"{key}: {value}" for key, value in inputs.items())


def _bank_path(scenario_name: str) -> Path:
    """Resolve the per-scenario question-bank JSON path."""
    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "schmidt"
        / "scenarios"
        / scenario_name
        / "protocol_probe_questions.json"
    )


@lru_cache(maxsize=8)
def _load_question_bank(scenario_name: str) -> dict[str, ProbeQuestionPrompt]:
    """Read the bank from disk once per ``(scenario_name)`` and index by ``question_id``."""
    bank_path = _bank_path(scenario_name=scenario_name)
    if not bank_path.exists():
        return {}
    raw = orjson.loads(bank_path.read_bytes())
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


def get_question_prompt(scenario_name: str, question_id: str) -> ProbeQuestionPrompt:
    """Return the display-ready prompt for ``question_id`` in ``scenario_name``.

    Falls back to a placeholder entry when the bank file is unavailable
    or the id is unknown — this keeps the tab rendering even on an
    older run that references retired questions.
    """
    bank = _load_question_bank(scenario_name=scenario_name)
    found = bank.get(question_id)
    if found is not None:
        return found
    return ProbeQuestionPrompt(
        question_id=question_id,
        agent_role_filter="unknown",
        display_text="(prompt not found in current bank)",
    )
