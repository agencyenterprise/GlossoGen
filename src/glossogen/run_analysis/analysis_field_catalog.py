"""What a selection can be sliced and measured by, read off the selection itself.

Built from the same observation table a query runs over, so every dimension offered
is one a group-by can key on and every measure offered is one that has numbers at
this grain. A metric that only reports a run-level score offers zero rows at the
round grain, and says so, rather than appearing choosable and charting empty.

Values are capped per dimension. The most common ones are kept, because those are
what a picker is for, and the true count travels beside them so a client can say
what it is not showing.
"""

from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_limits import (
    MAX_DIMENSION_VALUES,
    MAX_GROUP_BY_KEYS,
    MAX_RESULT_ROWS,
)
from glossogen.run_analysis.analysis_result_models import (
    AnalysisDimension,
    AnalysisDimensionValue,
    AnalysisFieldCatalog,
    AnalysisMeasureField,
)
from glossogen.run_analysis.analysis_run_record import AnalysisRunRecord
from glossogen.run_analysis.dimension_filter import parse_number
from glossogen.run_analysis.measure_resolution import (
    NUMERIC_RUN_COLUMNS,
    MeasureField,
    MeasureSource,
    field_key,
)
from glossogen.run_analysis.metric_inventory import (
    available_metric_names,
    keyed_metric_names,
    measure_unit,
    metric_units,
)
from glossogen.run_analysis.observation_row import ObservationRow
from glossogen.run_analysis.observation_table import (
    KEY_DIMENSION_PREFIX,
    build_observation_table,
    grain_dimension_keys,
)
from glossogen.run_export.export_column_catalog import column_group_of, humanize_column_key

COLUMN_GROUP_ROUND = "round"
COLUMN_GROUP_AGENT = "agent"
COLUMN_GROUP_METRIC_KEY = "metric_key"


def _dimension_group(key: str, grain: AnalysisGrain) -> str:
    """Return which family a dimension belongs to, including the grain's own keys."""
    if key.startswith(KEY_DIMENSION_PREFIX):
        return COLUMN_GROUP_METRIC_KEY
    grain_keys = grain_dimension_keys(grain=grain)
    if key in grain_keys:
        if grain is AnalysisGrain.ROUND:
            return COLUMN_GROUP_ROUND
        return COLUMN_GROUP_AGENT
    return column_group_of(key=key)


def _all_fields(records: list[AnalysisRunRecord], grain: AnalysisGrain) -> list[MeasureField]:
    """Return every measurable this grain can fill.

    The two metric name spaces do not overlap. A report's measurement names fill rows
    at the run, round and agent grains; the registry names that wrote sidecars fill
    rows at the keyed grain, and a metric scoring each channel separately reports
    ``language_repetition_team_a`` while registering as ``language_repetition``.
    Offering both lists at either grain would offer names that grain has no rows for.
    """
    if grain is AnalysisGrain.KEYED:
        names = keyed_metric_names(records=records)
    else:
        names = available_metric_names(records=records)
    fields = [MeasureField(source=MeasureSource.METRIC, key=name) for name in names]
    fields.extend(
        MeasureField(source=MeasureSource.RUN_COLUMN, key=column) for column in NUMERIC_RUN_COLUMNS
    )
    return fields


def _dimension_entries(
    rows: list[ObservationRow],
    grain: AnalysisGrain,
) -> list[AnalysisDimension]:
    """Describe every dimension the table's rows carry."""
    counts_by_key: dict[str, dict[str, int]] = {}
    for row in rows:
        for key, cell in row.dimensions.items():
            counts = counts_by_key.setdefault(key, {})
            counts[cell] = counts.get(cell, 0) + 1

    entries: list[AnalysisDimension] = []
    for key in sorted(counts_by_key):
        counts = counts_by_key[key]
        most_common = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        kept = most_common[:MAX_DIMENSION_VALUES]
        ordered = sorted(kept, key=lambda item: _value_order(value=item[0]))
        entries.append(
            AnalysisDimension(
                key=key,
                label=humanize_column_key(key=key),
                group=_dimension_group(key=key, grain=grain),
                rows_with_value=sum(count for cell, count in counts.items() if cell != ""),
                distinct_count=len(counts),
                values=[
                    AnalysisDimensionValue(value=value, observation_count=count)
                    for value, count in ordered
                ],
            )
        )
    return entries


def _value_order(value: str) -> tuple[int, float, str]:
    """Order a dimension's values, reading numeric ones as numbers."""
    number = parse_number(text=value)
    if number is None:
        return (1, 0.0, value)
    return (0, number, "")


def _measure_entries(
    rows: list[ObservationRow],
    fields: list[MeasureField],
    records: list[AnalysisRunRecord],
    grain: AnalysisGrain,
) -> list[AnalysisMeasureField]:
    """Describe every measurable, with how many rows at this grain carry a number."""
    units = metric_units(records=records)
    entries: list[AnalysisMeasureField] = []
    for field in fields:
        key = field_key(field=field)
        filled = sum(1 for row in rows if row.measures.get(key) is not None)
        unit = measure_unit(field=field, grain=grain, units=units)
        entries.append(
            AnalysisMeasureField(
                source=field.source.value,
                key=field.key,
                label=humanize_column_key(key=field.key),
                score_unit=unit,
                rows_with_value=filled,
            )
        )
    return entries


def build_field_catalog(
    records: list[AnalysisRunRecord],
    grain: AnalysisGrain,
) -> AnalysisFieldCatalog:
    """Describe what queries this selection can answer at one grain."""
    fields = _all_fields(records=records, grain=grain)
    rows = build_observation_table(records=records, grain=grain, fields=fields)
    return AnalysisFieldCatalog(
        grain=grain,
        run_count=len(records),
        observation_count=len(rows),
        runs_without_report=[record.run_id for record in records if not record.has_report],
        missing_run_ids=[],
        dimensions=_dimension_entries(rows=rows, grain=grain),
        measures=_measure_entries(rows=rows, fields=fields, records=records, grain=grain),
        max_dimension_values=MAX_DIMENSION_VALUES,
        max_group_by_keys=MAX_GROUP_BY_KEYS,
        max_result_rows=MAX_RESULT_ROWS,
    )
