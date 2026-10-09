"""Narrowing a table by what its dimension cells say.

Cells are text, because that is what a knob, a label, and a status all are once
they share a column space. The two numeric operators parse the cell and the bound
on the way past; a cell that is not a number fails the comparison rather than
passing it, so a knob missing on half a mixed-scenario selection cannot slip
through a range filter.

Emptiness is its own operator instead of a magic value, since a knob the run never
recorded and a knob recorded as the empty string are the same blank cell here, and
"" is a legitimate thing to ask for.
"""

import math
from enum import Enum
from typing import Self

from pydantic import BaseModel, model_validator

from glossogen.run_analysis.observation_row import ObservationRow


class FilterOperator(str, Enum):
    """How a filter compares a dimension cell against the values it carries."""

    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    GREATER_OR_EQUAL = "gte"
    LESS_OR_EQUAL = "lte"


class DimensionFilter(BaseModel):
    """One condition on one dimension.

    ``values`` holds the alternatives for ``in`` / ``not_in``, the substring for
    ``contains``, and the bound for the numeric operators. The emptiness operators
    ignore it.

    A comparing operator with no value is refused rather than applied. Empty is not a
    neutral filter: ``in`` with no values matches nothing and ``not_in`` with none
    matches everything, so a half-built filter would silently blank every chart on a
    dashboard one way and silently do nothing the other. The CLI already refused this
    spec by name; the refusal belongs on the model so every caller gets it.

    A numeric operator whose bound is not a number is refused for the same reason:
    applied, it would fail every row and blank the chart without saying why.
    """

    key: str
    operator: FilterOperator
    values: list[str]

    @model_validator(mode="after")
    def check_values(self) -> Self:
        """Refuse a comparing operator that carries nothing, or a bound that is no number."""
        if self.operator in _VALUELESS_OPERATORS:
            return self
        if not self.values:
            raise ValueError(
                f"The {self.operator.value!r} filter on {self.key!r} needs at least one "
                "value to compare against."
            )
        if self.operator in _NUMERIC_OPERATORS:
            if len(self.values) != 1:
                raise ValueError(
                    f"The {self.operator.value!r} filter on {self.key!r} needs exactly "
                    "one numeric bound."
                )
            if parse_number(text=self.values[0]) is None:
                raise ValueError(
                    f"The {self.operator.value!r} filter on {self.key!r} compares against "
                    f"{self.values[0]!r}, which is not a number."
                )
        return self


_VALUELESS_OPERATORS = frozenset({FilterOperator.IS_EMPTY, FilterOperator.IS_NOT_EMPTY})
_NUMERIC_OPERATORS = frozenset({FilterOperator.GREATER_OR_EQUAL, FilterOperator.LESS_OR_EQUAL})


def parse_number(text: str) -> float | None:
    """Parse a cell as a number, or ``None`` when it is not one.

    Shared with the result ordering, so a group of knob values sorts as numbers
    wherever the same cells are read as numbers.
    """
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    return number


def matches_filter(cell: str, dimension_filter: DimensionFilter) -> bool:
    """Return whether one cell satisfies one filter."""
    operator = dimension_filter.operator
    if operator is FilterOperator.IN:
        return cell in dimension_filter.values
    if operator is FilterOperator.NOT_IN:
        return cell not in dimension_filter.values
    if operator is FilterOperator.CONTAINS:
        return any(value.lower() in cell.lower() for value in dimension_filter.values)
    if operator is FilterOperator.IS_EMPTY:
        return cell == ""
    if operator is FilterOperator.IS_NOT_EMPTY:
        return cell != ""

    # The validator proved the bound parses; a cell that does not fails the filter.
    bound = parse_number(text=dimension_filter.values[0])
    number = parse_number(text=cell)
    if bound is None or number is None:
        return False
    if operator is FilterOperator.GREATER_OR_EQUAL:
        return number >= bound
    return number <= bound


def apply_filters(
    rows: list[ObservationRow],
    filters: list[DimensionFilter],
) -> list[ObservationRow]:
    """Return the rows satisfying every filter."""
    if not filters:
        return rows
    return [
        row
        for row in rows
        if all(
            matches_filter(
                cell=row.dimensions.get(dimension_filter.key, ""),
                dimension_filter=dimension_filter,
            )
            for dimension_filter in filters
        )
    ]
