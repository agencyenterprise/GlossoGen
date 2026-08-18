"""The long table: one row per run, metric, and agent observed.

Per-agent numbers are opt-in for a metric, and most do not report them, so this
table is often just a header. Empty is the honest answer there: a metric with a
perfectly good run-level score can have nothing to say per agent.

Because of that, the per-agent roster does not live here. Model, provider, and
role for every agent are carried on the run-level table as their own column
families, so the roster survives a run whose metrics reported nothing per agent.
The model and provider repeated on these rows are a convenience for grouping, and
are resolved from the same roster.
"""

from collections.abc import Iterator

from glossogen.run_export.agent_identity_columns import agent_model_by_id
from glossogen.run_export.csv_cell_text import render_cell
from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.metric_column_projection import measurements_by_name
from glossogen.run_export.run_context_columns import run_context_cells
from glossogen.run_export.run_metadata_columns import IDENTITY_COLUMNS

AGENT_LEVEL_FRAME_NAME = "agent_level"

OBSERVATION_COLUMNS: tuple[str, ...] = (
    "agent_id",
    "agent_role",
    "agent_model",
    "agent_provider",
    "metric_name",
    "score_unit",
    "value",
    "note",
)


def agent_level_header(columns: list[str], repeat_run_columns: bool) -> list[str]:
    """Return the frame's column names in emission order."""
    header = list(IDENTITY_COLUMNS)
    if repeat_run_columns:
        header.extend(key for key in columns if key not in IDENTITY_COLUMNS)
    header.extend(OBSERVATION_COLUMNS)
    return header


def build_agent_level_frame(
    records: list[ExportRunRecord],
    columns: list[str],
    metrics: list[str],
    repeat_run_columns: bool,
) -> CsvFrame:
    """Build the one-row-per-agent-observation table for the selected metrics."""
    wanted = list(metrics)

    def rows() -> Iterator[list[str]]:
        for record in records:
            if record.report is None:
                continue
            context = run_context_cells(record=record)
            prefix = [context.get(key, "") for key in IDENTITY_COLUMNS]
            if repeat_run_columns:
                prefix.extend(
                    context.get(key, "") for key in columns if key not in IDENTITY_COLUMNS
                )
            roster = agent_model_by_id(agent_models=record.summary.agent_models)
            measurements = measurements_by_name(measurements=record.report.measurements)
            for name in wanted:
                measurement = measurements.get(name)
                if measurement is None:
                    continue
                for observation in measurement.per_agent:
                    agent = roster.get(observation.agent_id)
                    role = ""
                    model = ""
                    provider = ""
                    if agent is not None:
                        role = agent.role_name
                        model = agent.model
                        provider = agent.provider
                    yield prefix + [
                        render_cell(text=observation.agent_id),
                        render_cell(text=role),
                        render_cell(text=model),
                        render_cell(text=provider),
                        name,
                        render_cell(text=measurement.score_unit),
                        str(observation.value),
                        render_cell(text=observation.note),
                    ]

    return CsvFrame(
        name=AGENT_LEVEL_FRAME_NAME,
        header=agent_level_header(columns=columns, repeat_run_columns=repeat_run_columns),
        rows=rows(),
    )
