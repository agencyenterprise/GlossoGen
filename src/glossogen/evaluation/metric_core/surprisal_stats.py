"""Mean and spread for the per-round message-score metrics.

``primary_channel_message_scores`` averages per-message scores within a round
and then averages the per-round means. These helpers give both steps the same
empty- and single-value semantics (``0.0`` rather than raising).
"""

import math


def mean(values: list[float]) -> float:
    """Arithmetic mean; returns 0.0 for an empty list."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def population_std(values: list[float], value_mean: float) -> float:
    """Population standard deviation; returns 0.0 for fewer than two values."""
    if len(values) < 2:
        return 0.0
    variance = sum((value - value_mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)
