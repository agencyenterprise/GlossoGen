"""The columns describing a run itself, before knobs or scores.

A curated projection of the run summary, not every field on it. The omissions are
deliberate: the scenario description is prose that repeats identically on every row
of a single-scenario export, and the evaluation content hash addresses a cache and
says nothing about the run.

`run_id` and `scenario_name` are always emitted and cannot be deselected. Every
other frame joins back on `run_id`, and a CSV whose rows cannot be identified is
not worth writing.
"""

from glossogen.run_export.csv_cell_text import render_cell, render_scalar, render_string_list
from glossogen.run_export.model_weight_class import MODEL_CLASS_COLUMN, model_class_of
from glossogen.server.runs.models import RunSummary

RUN_ID_COLUMN = "run_id"
SCENARIO_NAME_COLUMN = "scenario_name"

IDENTITY_COLUMNS: tuple[str, ...] = (RUN_ID_COLUMN, SCENARIO_NAME_COLUMN)


def run_metadata_cells(summary: RunSummary) -> dict[str, str]:
    """Return the identity and metadata cells for one run."""
    return {
        RUN_ID_COLUMN: render_cell(text=summary.run_id),
        SCENARIO_NAME_COLUMN: render_cell(text=summary.scenario_name),
        "run_dir_name": render_cell(text=summary.run_id.split("/", 1)[-1]),
        "timestamp": summary.timestamp.isoformat(),
        "status": render_cell(text=summary.status.value),
        "current_round": render_scalar(value=summary.current_round),
        "total_messages": render_scalar(value=summary.total_messages),
        "total_cost_usd": render_scalar(value=summary.total_cost_usd),
        "duration_seconds": render_scalar(value=summary.duration_seconds),
        "provider": render_cell(text=summary.provider),
        MODEL_CLASS_COLUMN: model_class_of(agent_models=summary.agent_models),
        "models": render_string_list(values=summary.models),
        "labels": render_string_list(values=summary.labels),
        "has_evaluation": render_scalar(value=summary.has_evaluation),
        "has_note": render_scalar(value=summary.has_note),
        "run_dir": render_cell(text=summary.run_dir),
    }
