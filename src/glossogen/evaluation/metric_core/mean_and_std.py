"""Mean and population standard deviation that return ``0.0`` instead of raising.

The mean of an empty list and the spread of fewer than two values are both
``0.0``, so a round with one message reports no spread rather than failing.
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
