"""Where a derived run came from, as columns.

A run can be a fork, a replace-agent, a cross-run replace-agent, or a
resume-at-round, and each records a different set of fields. That could be four
column families a reader has to keep straight. Instead there is one
`derivation_type` naming which kind it is, and one `lineage.*` family flattened from
whichever provenance model is populated.

`lineage.source_run_id` matters most and every kind carries it, so a chain of
resumes can be walked from the CSV alone. Cross-run runs have two parents: they fill
`lineage.source_a_run_id` and `lineage.source_b_run_id`, and leave
`lineage.source_run_id` empty.
"""

from pydantic import BaseModel

from glossogen.run_export.csv_cell_text import render_scalar
from glossogen.server.runs.models import RunSummary

DERIVATION_TYPE_COLUMN = "derivation_type"
LINEAGE_COLUMN_PREFIX = "lineage."


def _lineage_of(summary: RunSummary) -> tuple[str, BaseModel | None]:
    """Return the run's derivation type and the provenance model carrying it."""
    if summary.fork_source is not None:
        return ("fork", summary.fork_source)
    if summary.cross_run_replace_agent_source is not None:
        return ("cross_run_replace_agent", summary.cross_run_replace_agent_source)
    if summary.replace_agent_source is not None:
        return ("replace_agent", summary.replace_agent_source)
    if summary.resume_at_round_source is not None:
        return ("resume_at_round", summary.resume_at_round_source)
    return ("", None)


def lineage_cells(summary: RunSummary) -> dict[str, str]:
    """Return the derivation type and flattened provenance cells for one run."""
    derivation_type, source = _lineage_of(summary=summary)
    cells: dict[str, str] = {DERIVATION_TYPE_COLUMN: derivation_type}
    if source is None:
        return cells
    for field_name, value in source.model_dump().items():
        cells[f"{LINEAGE_COLUMN_PREFIX}{field_name}"] = render_scalar(value=value)
    return cells
