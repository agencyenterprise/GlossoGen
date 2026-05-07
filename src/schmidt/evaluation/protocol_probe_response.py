"""Pydantic models for the protocol probe metric.

``ProtocolProbeOutput`` is the structured output schema enforced on the LLM
when answering a probe question. ``ProtocolProbeResponse`` is the row schema
written to ``protocol_probe_responses.jsonl`` inside each run directory.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ProtocolProbeOutput(BaseModel):
    """Structured output the probe agent must emit for every probe question."""

    reasoning: str = Field(
        description=(
            "Brief reasoning for how the hypothetical input maps to the protocol "
            "the agent and its teammate developed during the simulation. Cite "
            "specific conventions, abbreviations, or codes the agent is invoking. "
            "Not sent to the teammate — used by the evaluator to debug surprising "
            "messages."
        )
    )
    message: str = Field(
        description=(
            "The exact text the agent would send on #link in response to the "
            "hypothetical input, using the protocol the agent and its teammate "
            "developed during the simulation. Just the message body, as if "
            "calling send_message — no quoting, no preamble, no explanation."
        )
    )


class ProtocolProbeResponse(BaseModel):
    """One row in ``protocol_probe_responses.jsonl``.

    The rendered prompt text is intentionally not stored — it can always be
    reconstructed from ``question_id`` plus the test bank file and the
    Jinja2 templates.
    """

    timestamp: datetime
    replica_index: int
    agent_id: str
    role_name: str
    model: str
    provider: str
    question_id: str
    question_role_filter: str
    cutoff_round: int | None
    reasoning_text: str
    response_text: str
