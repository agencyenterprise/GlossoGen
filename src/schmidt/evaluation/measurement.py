"""Data models for the per-metric measurement output of an evaluation run.

Replaces the verdict-shaped ``MetricResult`` with a numeric-shaped
``Measurement`` that carries an overall scalar score, a unit string, and
structured per-round / per-agent observations. Every metric in the codebase
returns one or more ``Measurement`` instances from its ``compute`` method.
"""

from pydantic import BaseModel, Field


class RoundNote(BaseModel):
    """A single per-round note returned by an LLM judge.

    Used inside judge output schemas so each round where the phenomenon was
    observed carries the judge's specific reasoning for that round. Maps
    1:1 to a ``RoundObservation`` in the resulting ``Measurement``.
    """

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
    value: float
    note: str


class AgentObservation(BaseModel):
    """One agent's contribution to a Measurement.

    Used only when an agent-level breakdown is meaningful (e.g.
    content_filter_refusal per agent). Empty list otherwise.
    """

    agent_id: str
    value: float
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
    score: float
    score_unit: str
    summary: str
    per_round: list[RoundObservation]
    per_agent: list[AgentObservation]
