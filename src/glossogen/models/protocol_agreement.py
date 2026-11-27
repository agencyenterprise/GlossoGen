"""How the agents of one run came to share each convention, with the messages that show each step.

The ``protocol_agreement`` metric writes this as a sidecar in the run directory and the
run page reads it back. Every piece of evidence names a message or tool call by the id
the run page uses for it, so the page can jump to it.
"""

from enum import StrEnum

from pydantic import BaseModel


class AgreementStage(StrEnum):
    """One step in how a convention spread: an agent first used it, or another agent
    showed that it understood it."""

    PROPOSED = "proposed"
    UNDERSTOOD = "understood"


class EvidenceMessage(BaseModel):
    """One channel message or tool call cited as evidence.

    ``message_id`` is the id the run page uses for the entry: the message's own id,
    or ``{event_id}-{call_id}`` for a tool call. ``text`` is the entry as the judge
    read it, copied from the event log rather than written by the judge.
    """

    message_id: str
    round_number: int
    agent_id: str
    text: str


class AgreementStep(BaseModel):
    """One stage of a convention, with the judge's reading of it and its evidence.

    ``round_number`` and ``agent_id`` are those of the first evidence entry.
    """

    stage: AgreementStage
    round_number: int
    agent_id: str
    explanation: str
    evidence: list[EvidenceMessage]


class ProtocolConvention(BaseModel):
    """One rule the agents used to read or write their signals, and how it spread.

    ``first_shared_round`` is the first round in which every agent used the
    convention, or ``None`` when not every agent did.
    """

    name: str
    meaning: str
    steps: list[AgreementStep]
    adopted_by_all: bool
    first_shared_round: int | None


class ProtocolAgreementReport(BaseModel):
    """The ``protocol_agreement`` sidecar: the judge's summary and each convention it found."""

    summary: str
    conventions: list[ProtocolConvention]
