"""How a column of observations becomes one number, and what a blank does to it.

A missing value is dropped before anything is computed, never replaced by zero.
The count of what was dropped travels beside the result, so a mean over three of
twenty runs is visibly that rather than a confident-looking number.

`count` counts the values that existed. A group where every value is missing
aggregates to nothing at all, which is the same claim the export's empty cell
makes.
"""

import math
import statistics
from enum import Enum


class Aggregate(str, Enum):
    """How the values in one group are reduced to a single number."""

    MEAN = "mean"
    MEDIAN = "median"
    SUM = "sum"
    COUNT = "count"
    MIN = "min"
    MAX = "max"
    STDDEV = "stddev"
    SEM = "sem"


def present_values(values: list[float | None]) -> list[float]:
    """Return the values that exist, dropping missing ones and NaNs."""
    present: list[float] = []
    for value in values:
        if value is None:
            continue
        if math.isnan(value):
            continue
        present.append(value)
    return present


def aggregate_values(values: list[float], aggregate: Aggregate) -> float | None:
    """Reduce present values to one number, or ``None`` when it cannot be computed.

    ``stddev`` and ``sem`` need two values; one observation has no spread, and
    reporting ``0.0`` there would read as a measured absence of variance.
    """
    if aggregate is Aggregate.COUNT:
        return float(len(values))
    if not values:
        return None
    if aggregate is Aggregate.MEAN:
        return statistics.fmean(values)
    if aggregate is Aggregate.MEDIAN:
        return statistics.median(values)
    if aggregate is Aggregate.SUM:
        return math.fsum(values)
    if aggregate is Aggregate.MIN:
        return min(values)
    if aggregate is Aggregate.MAX:
        return max(values)
    if len(values) < 2:
        return None
    deviation = statistics.stdev(values)
    if aggregate is Aggregate.STDDEV:
        return deviation
    return deviation / math.sqrt(len(values))
