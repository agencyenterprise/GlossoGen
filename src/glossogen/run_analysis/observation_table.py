"""Turning selected runs into rows an analysis can group.

Each grain reproduces the corresponding CSV frame's row rule, so a chart and the
exported table it would come from cover the same observations:

- run: one row per run, whether or not it was evaluated.
- round: one row per (run, round) that at least one selected metric reported.
  A round nothing reported has no row, which is "no observation" and not a zero.
- agent: one row per agent on the run's registered roster, plus any agent only a
  metric named, so a per-agent number is never dropped for missing the roster.
- keyed: one row per observation a metric reported beside its report. The keys are the
  metric's own, so the dimensions this grain adds are discovered from the data rather
  than declared here. Rows are never shared between metrics, even where two used the
  same keys: each observation gets its own, and the metrics that said nothing about it
  leave their cells blank. Grouping is what brings them back together, which is the
  same way every other grain works.

Dimensions are the run's context cells plus whatever the grain adds. Measures are
resolved per field, and a field with no number for that row holds ``None``.
"""

from glossogen.run_analysis.analysis_grain import AnalysisGrain
from glossogen.run_analysis.analysis_run_record import AnalysisRunRecord
from glossogen.run_analysis.measure_resolution import MeasureField, MeasureSource, field_key
from glossogen.run_analysis.observation_row import ObservationRow
from glossogen.run_export.round_level_frame import ROUND_NUMBER_COLUMN

ROUND_NUMBER_DIMENSION = ROUND_NUMBER_COLUMN

# The agent grain's own dimension names, matching the export's agent table. Declared
# here rather than unpacked from its `AGENT_COLUMNS`: that tuple is typed
# `tuple[str, ...]`, so an arity change is invisible to the type checker, and an
# unpack of it would raise at import time. The server would then stop booting because
# the export grew a column. Declaring them also keeps this grain offering exactly the
# dimensions it fills.
AGENT_ID_DIMENSION = "agent_id"
AGENT_ROLE_DIMENSION = "agent_role"
AGENT_MODEL_DIMENSION = "agent_model"
AGENT_PROVIDER_DIMENSION = "agent_provider"

KEY_DIMENSION_PREFIX = "key."


def grain_dimension_keys(grain: AnalysisGrain) -> tuple[str, ...]:
    """Return the dimension keys a grain adds on top of the run's context.

    The keyed grain adds whatever the metrics used, which is not knowable without
    reading them, so it declares none here and the catalog reports what it found.
    """
    if grain is AnalysisGrain.ROUND:
        return (ROUND_NUMBER_DIMENSION,)
    if grain is AnalysisGrain.AGENT:
        return (
            AGENT_ID_DIMENSION,
            AGENT_ROLE_DIMENSION,
            AGENT_MODEL_DIMENSION,
            AGENT_PROVIDER_DIMENSION,
        )
    return ()


def _keyed_rows(
    records: list[AnalysisRunRecord],
    fields: list[MeasureField],
) -> list[ObservationRow]:
    """Build one row per (run, key tuple) the selected metrics reported."""
    wanted = {field.key for field in fields if field.source is MeasureSource.METRIC}
    rows: list[ObservationRow] = []
    for record in records:
        run_columns = {
            field_key(field=field): _run_column(record=record, key=field.key)
            for field in fields
            if field.source is MeasureSource.RUN_COLUMN
        }
        for metric_name, observations in record.keyed.items():
            if metric_name not in wanted:
                continue
            column = field_key(field=MeasureField(source=MeasureSource.METRIC, key=metric_name))
            for observation in observations:
                dimensions = dict(record.dimensions)
                for name, value in observation.keys.items():
                    dimensions[f"{KEY_DIMENSION_PREFIX}{name}"] = value
                measures: dict[str, float | None] = {
                    field_key(field=field): None
                    for field in fields
                    if field.source is MeasureSource.METRIC
                }
                measures.update(run_columns)
                measures[column] = observation.value
                rows.append(
                    ObservationRow(
                        run_id=record.run_id,
                        dimensions=dimensions,
                        measures=measures,
                    )
                )
    return rows


def _run_column(record: AnalysisRunRecord, key: str) -> float | None:
    """Return one numeric run column, or ``None`` when the name is not one."""
    return record.run_columns.get(key)


def _run_level_measures(
    record: AnalysisRunRecord,
    fields: list[MeasureField],
) -> dict[str, float | None]:
    """Return one run's value for every requested field."""
    values: dict[str, float | None] = {}
    for field in fields:
        if field.source is MeasureSource.RUN_COLUMN:
            values[field_key(field=field)] = _run_column(record=record, key=field.key)
            continue
        metric = record.metrics.get(field.key)
        if metric is None:
            values[field_key(field=field)] = None
            continue
        values[field_key(field=field)] = metric.score
    return values


def _run_rows(
    records: list[AnalysisRunRecord],
    fields: list[MeasureField],
) -> list[ObservationRow]:
    """Build one row per run."""
    return [
        ObservationRow(
            run_id=record.run_id,
            # Copied like every other grain's: the record is shared with the cache and
            # outlives this table, so handing out its dict would let a later caller's
            # mutation reach another query's rows.
            dimensions=dict(record.dimensions),
            measures=_run_level_measures(record=record, fields=fields),
        )
        for record in records
    ]


def _round_rows(
    records: list[AnalysisRunRecord],
    fields: list[MeasureField],
) -> list[ObservationRow]:
    """Build one row per (run, round) some selected metric reported."""
    rows: list[ObservationRow] = []
    for record in records:
        observed = {
            field.key: record.metrics[field.key].per_round
            for field in fields
            if field.source is MeasureSource.METRIC and field.key in record.metrics
        }
        round_numbers = sorted({number for by_round in observed.values() for number in by_round})
        if not round_numbers:
            continue

        for round_number in round_numbers:
            measures: dict[str, float | None] = {}
            for field in fields:
                if field.source is MeasureSource.RUN_COLUMN:
                    measures[field_key(field=field)] = _run_column(record=record, key=field.key)
                    continue
                measures[field_key(field=field)] = observed.get(field.key, {}).get(round_number)

            dimensions = dict(record.dimensions)
            dimensions[ROUND_NUMBER_DIMENSION] = str(round_number)
            rows.append(
                ObservationRow(
                    run_id=record.run_id,
                    dimensions=dimensions,
                    measures=measures,
                )
            )
    return rows


def _agent_rows(
    records: list[AnalysisRunRecord],
    fields: list[MeasureField],
) -> list[ObservationRow]:
    """Build one row per agent on each run's roster, plus agents only a metric named."""
    rows: list[ObservationRow] = []
    for record in records:
        roster = {agent.agent_id: agent for agent in record.agents}
        observed = {
            field.key: record.metrics[field.key].per_agent
            for field in fields
            if field.source is MeasureSource.METRIC and field.key in record.metrics
        }

        agent_ids = list(roster)
        for by_agent in observed.values():
            agent_ids.extend(agent_id for agent_id in by_agent if agent_id not in roster)
        agent_ids = list(dict.fromkeys(agent_ids))
        if not agent_ids:
            continue

        for agent_id in agent_ids:
            agent = roster.get(agent_id)
            role = ""
            model = ""
            provider = ""
            if agent is not None:
                role = agent.role_name
                model = agent.model
                provider = agent.provider

            measures: dict[str, float | None] = {}
            for field in fields:
                if field.source is MeasureSource.RUN_COLUMN:
                    measures[field_key(field=field)] = _run_column(record=record, key=field.key)
                    continue
                measures[field_key(field=field)] = observed.get(field.key, {}).get(agent_id)

            dimensions = dict(record.dimensions)
            dimensions[AGENT_ID_DIMENSION] = agent_id
            dimensions[AGENT_ROLE_DIMENSION] = role
            dimensions[AGENT_MODEL_DIMENSION] = model
            dimensions[AGENT_PROVIDER_DIMENSION] = provider
            rows.append(
                ObservationRow(
                    run_id=record.run_id,
                    dimensions=dimensions,
                    measures=measures,
                )
            )
    return rows


def build_observation_table(
    records: list[AnalysisRunRecord],
    grain: AnalysisGrain,
    fields: list[MeasureField],
) -> list[ObservationRow]:
    """Build the rows a query filters, groups, and aggregates."""
    unique_fields = list(dict.fromkeys(fields))
    if grain is AnalysisGrain.KEYED:
        return _keyed_rows(records=records, fields=unique_fields)
    if grain is AnalysisGrain.ROUND:
        return _round_rows(records=records, fields=unique_fields)
    if grain is AnalysisGrain.AGENT:
        return _agent_rows(records=records, fields=unique_fields)
    return _run_rows(records=records, fields=unique_fields)
