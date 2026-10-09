"""The row the `language_repetition` metric writes per judged message, and its file name.

The metric writes one JSON line per message; the metric's keyed-observation reader
and the export's message table read them back.
"""

from pydantic import BaseModel

LANGUAGE_REPETITION_SIDECAR_FILENAME = "language_repetition_messages.jsonl"


class MessageRepetitionRow(BaseModel):
    """One judged message: where it was sent and its replica-averaged redundancy factor."""

    round_number: int
    message_number: int
    message_id: str
    channel_id: str
    sender_agent_id: str
    repetition_factor: float
    replica_factors: list[float]
