"""What a query can measure: an evaluator's score, or a number the run itself carries.

Metric names come from the reports the selected runs carry, exactly as the export's
columns do, so a metric nobody here has heard of is measurable the moment a report
names it.

The run columns are the numeric ones on the run summary. They are what a cohort gets
compared on when the question is about cost or length rather than about a score, and
they exist on runs that were never evaluated.

At the round and agent grains a run column carries the run's own value on every row.
That is the run's number repeated, not a per-round one, so a mean over it is the
run's value and a sum over it is that value times the number of rows.
"""

from collections.abc import Callable
from enum import Enum
from typing import NamedTuple

from glossogen.server.runs.models import RunSummary


class MeasureSource(str, Enum):
    """Where a measure's numbers come from."""

    METRIC = "metric"
    RUN_COLUMN = "run_column"


class MeasureField(NamedTuple):
    """One measurable quantity, before any aggregate is chosen for it."""

    source: MeasureSource
    key: str


def field_key(field: MeasureField) -> str:
    """Return the key a field's values are held under on an observation row."""
    return f"{field.source.value}:{field.key}"


class RunColumn(NamedTuple):
    """One numeric column the run itself carries: how to read it, and its unit."""

    unit: str
    read: Callable[[RunSummary], float]


def _current_round(summary: RunSummary) -> float:
    """Read the run's current round as a number."""
    return float(summary.current_round)


def _total_messages(summary: RunSummary) -> float:
    """Read the run's message count as a number."""
    return float(summary.total_messages)


def _total_cost_usd(summary: RunSummary) -> float:
    """Read the run's cost."""
    return summary.total_cost_usd


def _duration_seconds(summary: RunSummary) -> float:
    """Read the run's wall-clock duration."""
    return summary.duration_seconds


# The single description of the run columns. The names, the units and the readers were
# three parallel structures that happened to agree; adding a column meant editing all
# three, and missing one failed nothing.
RUN_COLUMNS: dict[str, RunColumn] = {
    "current_round": RunColumn(unit="rounds", read=_current_round),
    "total_messages": RunColumn(unit="messages", read=_total_messages),
    "total_cost_usd": RunColumn(unit="USD", read=_total_cost_usd),
    "duration_seconds": RunColumn(unit="seconds", read=_duration_seconds),
}

NUMERIC_RUN_COLUMNS: tuple[str, ...] = tuple(RUN_COLUMNS)

RUN_COLUMN_UNITS: dict[str, str] = {name: column.unit for name, column in RUN_COLUMNS.items()}


def run_column_values(summary: RunSummary) -> dict[str, float]:
    """Return every numeric run column for one run."""
    return {name: column.read(summary) for name, column in RUN_COLUMNS.items()}
