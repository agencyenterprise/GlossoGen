"""What a metric returns from ``compute``.

A ``Measurement`` is numeric rather than a verdict: one scalar ``score``, a
``score_unit`` naming what the number counts, and optional per-round and
per-agent observations. The unit matters because scores are not comparable
across metrics; one counts rounds, another averages nats per token.

A metric may return several, which is how a multi-team scenario reports one
result per team.
"""

from pydantic import BaseModel, Field, FiniteFloat


class RoundNote(BaseModel):
    """One observation returned by an LLM judge for a round."""

    round_number: int = Field(
        description="The round number where the observation was made.",
    )
    note: str = Field(
        description="What the judge specifically observed in this round, with examples.",
    )


class RoundObservation(BaseModel):
    """One round's structured contribution to a Measurement.

    A metric only emits a RoundObservation for rounds it has something to
    say about. Pure metrics (perplexity, mlu) emit one per round with
    messages; flag-style metrics (neologism, round_ended_idle) emit one
    per round where the phenomenon fired.
    """

    round_number: int
    value: FiniteFloat
    note: str


class AgentObservation(BaseModel):
    """One agent's contribution to a Measurement.

    Used only when an agent-level breakdown is meaningful (e.g.
    content_filter_refusal per agent). Empty list otherwise.
    """

    agent_id: str
    value: FiniteFloat
    note: str


class Measurement(BaseModel):
    """Numeric measurement result for a single metric applied to a run.

    ``score`` is the metric's overall scalar (mean, fraction, count, ...).
    ``score_unit`` is a free-form human-readable label describing what
    ``score`` represents. ``summary`` is a one-line rollup.
    ``per_round`` and ``per_agent`` carry structured breakdowns that
    downstream tools can plot or filter without re-parsing strings.
    """

    metric_name: str
    score: FiniteFloat
    score_unit: str
    summary: str
    per_round: list[RoundObservation]
    per_agent: list[AgentObservation]


def merge_round_notes(notes: list[RoundNote]) -> list[RoundObservation]:
    """Merge judge notes by round so a round contributes at most once to a count."""
    notes_by_round: dict[int, list[str]] = {}
    for note in notes:
        notes_by_round.setdefault(note.round_number, []).append(note.note)
    return [
        RoundObservation(
            round_number=round_number,
            value=1.0,
            note="\n".join(round_notes),
        )
        for round_number, round_notes in notes_by_round.items()
    ]
