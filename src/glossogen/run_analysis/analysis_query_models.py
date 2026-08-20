"""What a client asks an analysis for.

The query is split from the selection it runs over. A saved dashboard carries one
selection and its charts carry queries, so re-pointing a whole dashboard at another
cohort is one field changing rather than every chart being rewritten. The endpoint
body puts them back together.

Group-by keys are ordered: the first is the x axis, the second the series. Naming
them by position rather than by role keeps the query shape independent of which
chart eventually draws it.
"""

from enum import Enum
from typing import Self

from pydantic import BaseModel, model_validator

from glossogen.run_analysis.aggregation import Aggregate
from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_limits import MAX_GROUP_BY_KEYS, MAX_RESULT_ROWS
from glossogen.run_analysis.dimension_filter import DimensionFilter
from glossogen.run_analysis.measure_resolution import MeasureField, MeasureSource
from glossogen.run_export.export_request_models import RunSelection

# At these grains a row exists only because some metric reported an observation:
# a round nothing scored has no row, and a sidecar key nothing wrote has none either.
# The run and agent grains are rowed by the run and its roster instead, so a run
# column alone is answerable there.
_GRAINS_ROWED_BY_METRICS = frozenset({AnalysisGrain.ROUND, AnalysisGrain.KEYED})


class MeasureSpec(BaseModel):
    """One measured quantity and how its values are reduced within a group."""

    source: MeasureSource
    key: str
    aggregate: Aggregate

    def field(self) -> MeasureField:
        """Return the measurable this spec reads, without its aggregate."""
        return MeasureField(source=self.source, key=self.key)

    def column_key(self) -> str:
        """Return a stable key naming this measure and its aggregate."""
        return f"{self.source.value}.{self.key}:{self.aggregate.value}"


class ResultSort(str, Enum):
    """How the result rows are ordered."""

    GROUP = "group"
    MEASURE_ASCENDING = "measure_ascending"
    MEASURE_DESCENDING = "measure_descending"


class AnalysisQuerySpec(BaseModel):
    """A question about a set of runs, without saying which runs.

    ``sort_measure_index`` says which measure a measure sort orders by. It is required
    rather than optional because a spec that sorts by a measure without naming it is
    not answerable, and a default would hide that.
    """

    grain: AnalysisGrain
    filters: list[DimensionFilter]
    group_by: list[str]
    measures: list[MeasureSpec]
    sort: ResultSort
    sort_measure_index: int
    limit: int

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        """Refuse a spec that cannot be answered."""
        if not self.measures:
            raise ValueError("Choose at least one measure.")
        if self.grain in _GRAINS_ROWED_BY_METRICS:
            if not any(measure.source is MeasureSource.METRIC for measure in self.measures):
                raise ValueError(
                    f"The {self.grain.value} grain has a row only where a metric reported "
                    "one, so a query at this grain needs at least one metric measure. A "
                    "run column alone would match no rows and answer with nothing."
                )
        if len(self.group_by) > MAX_GROUP_BY_KEYS:
            raise ValueError(f"At most {MAX_GROUP_BY_KEYS} group-by keys, one per chart axis.")
        if len(set(self.group_by)) != len(self.group_by):
            raise ValueError("Group-by keys must be distinct.")
        if self.sort is not ResultSort.GROUP:
            if not 0 <= self.sort_measure_index < len(self.measures):
                raise ValueError("sort_measure_index does not name one of the measures.")
        if not 1 <= self.limit <= MAX_RESULT_ROWS:
            raise ValueError(f"limit must be between 1 and {MAX_RESULT_ROWS}.")
        return self

    def fields(self) -> list[MeasureField]:
        """Return the measurables this spec reads, deduplicated in request order."""
        return list(dict.fromkeys(measure.field() for measure in self.measures))


class AnalysisQueryRequest(BaseModel):
    """Body for the analysis query endpoint: which runs, and what to ask of them."""

    selection: RunSelection
    query: AnalysisQuerySpec


class AnalysisFieldsRequest(BaseModel):
    """Body for the field catalog: which runs, and at which grain."""

    selection: RunSelection
    grain: AnalysisGrain
