"""The per-agent table: one row per run and agent, one column per metric.

Rows come from the run's registered agents, not from the metrics. Per-agent
numbers are opt-in and most metrics report none, so keying on the roster is what
keeps this table useful: it is the roster of who ran under which model, and the
metric columns fill in where a metric had something to say. Keyed on the
observations instead, it was usually a bare header.

An agent that only a metric knows about still gets a row, so an observation is
never dropped for naming an id the roster is missing. Its identity cells are
empty, which reads as the roster not carrying it.
"""

from collections.abc import Iterator

from glossogen.evaluation.metric_core.measurement import AgentObservation
from glossogen.run_export.agent_identity_columns import agent_model_by_id
from glossogen.run_export.csv_cell_text import render_cell
from glossogen.run_export.csv_frame import CsvFrame
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.metric_column_projection import (
    METRIC_COLUMN_PREFIX,
    METRIC_NOTE_COLUMN_PREFIX,
    agents_by_id,
    measurements_by_name,
    observation_note_cell,
    observation_value_cell,
)
from glossogen.run_export.run_context_columns import run_context_cells
from glossogen.run_export.run_metadata_columns import IDENTITY_COLUMNS

AGENT_LEVEL_FRAME_NAME = "agent_level"

AGENT_COLUMNS: tuple[str, ...] = (
    "agent_id",
    "agent_role",
    "agent_model",
    "agent_provider",
)


def agent_level_header(
    columns: list[str],
    metrics: list[str],
    repeat_run_columns: bool,
    include_metric_summaries: bool,
) -> list[str]:
    """Return the frame's column names in emission order."""
    header = list(IDENTITY_COLUMNS)
    if repeat_run_columns:
        header.extend(key for key in columns if key not in IDENTITY_COLUMNS)
    header.extend(AGENT_COLUMNS)
    header.extend(f"{METRIC_COLUMN_PREFIX}{name}" for name in metrics)
    if include_metric_summaries:
        header.extend(f"{METRIC_NOTE_COLUMN_PREFIX}{name}" for name in metrics)
    return header


def build_agent_level_frame(
    records: list[ExportRunRecord],
    columns: list[str],
    metrics: list[str],
    repeat_run_columns: bool,
    include_metric_summaries: bool,
) -> CsvFrame:
    """Build the one-row-per-agent table for the selected metrics."""
    wanted = list(metrics)

    def rows() -> Iterator[list[str]]:
        for record in records:
            roster = agent_model_by_id(agent_models=record.summary.agent_models)
            observed: dict[str, dict[str, AgentObservation]] = {}
            if record.report is not None:
                measurements = measurements_by_name(measurements=record.report.measurements)
                observed = {
                    name: agents_by_id(measurement=measurements[name])
                    for name in wanted
                    if name in measurements
                }

            agent_ids = list(roster)
            for by_agent in observed.values():
                for agent_id in by_agent:
                    if agent_id not in roster:
                        agent_ids.append(agent_id)
            agent_ids = list(dict.fromkeys(agent_ids))
            if not agent_ids:
                continue

            context = run_context_cells(record=record)
            prefix = [context.get(key, "") for key in IDENTITY_COLUMNS]
            if repeat_run_columns:
                prefix.extend(
                    context.get(key, "") for key in columns if key not in IDENTITY_COLUMNS
                )

            for agent_id in agent_ids:
                agent = roster.get(agent_id)
                role = ""
                model = ""
                provider = ""
                if agent is not None:
                    role = agent.role_name
                    model = agent.model
                    provider = agent.provider
                row = prefix + [
                    render_cell(text=agent_id),
                    render_cell(text=role),
                    render_cell(text=model),
                    render_cell(text=provider),
                ]
                row.extend(
                    observation_value_cell(observation=observed.get(name, {}).get(agent_id))
                    for name in wanted
                )
                if include_metric_summaries:
                    row.extend(
                        observation_note_cell(observation=observed.get(name, {}).get(agent_id))
                        for name in wanted
                    )
                yield row

    return CsvFrame(
        name=AGENT_LEVEL_FRAME_NAME,
        header=agent_level_header(
            columns=columns,
            metrics=metrics,
            repeat_run_columns=repeat_run_columns,
            include_metric_summaries=include_metric_summaries,
        ),
        rows=rows(),
    )
