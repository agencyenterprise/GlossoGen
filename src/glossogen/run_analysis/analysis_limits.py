"""Ceilings on what one analysis query may return.

The selection is bounded by the export's own run ceiling, since a query resolves
its runs the same way an export does. What is bounded here is the answer: a
group-by on a dimension whose values are nearly unique (a run id, a timestamp)
would otherwise return a row per run, and a chart with five thousand categories
is a download rather than a picture.

Two group-by keys, because a chart has an x axis and a series, and a third would
have nowhere to go.
"""

MAX_GROUP_BY_KEYS = 2

MAX_RESULT_ROWS = 5_000

MAX_DIMENSION_VALUES = 200
