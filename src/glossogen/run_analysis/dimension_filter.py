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
    """

    key: str
    operator: FilterOperator
    values: list[str]

    @model_validator(mode="after")
    def check_values(self) -> Self:
        """Refuse a comparing operator that carries nothing to compare against."""
        if self.operator in _VALUELESS_OPERATORS:
            return self
        if not self.values:
            raise ValueError(
                f"The {self.operator.value!r} filter on {self.key!r} needs at least one "
                "value to compare against."
            )
        return self


_VALUELESS_OPERATORS = frozenset({FilterOperator.IS_EMPTY, FilterOperator.IS_NOT_EMPTY})


def parse_number(text: str) -> float | None:
    """Parse a cell as a number, or ``None`` when it is not one.

    Shared with the result ordering, so a group of knob values sorts as numbers
    wherever the same cells are read as numbers.
    """
    try:
        return float(text)
    except ValueError:
        return None


def _first_bound(values: list[str]) -> float | None:
    """Return the numeric bound a range filter carries, or ``None`` when it has none."""
    if not values:
        return None
    return parse_number(text=values[0])


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

    bound = _first_bound(values=dimension_filter.values)
    number = parse_number(text=cell)
    if bound is None:
        return False
    if number is None:
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
