"""Every non-metric column a run contributes, merged and keyed.

Five families come together here: run metadata, knobs, `key=value` labels,
per-agent identity, and lineage. Each gets a prefix, because a flat merge would
collide. A scenario is free to declare a knob called `status` or `labels`, and
`perplexity` is both a plausible knob name and a metric name. The prefix makes a
column's origin readable from its name.

The available keys are the union across the selected runs, so a mixed-scenario
export has columns that only some rows fill. The export preview reports that
sparseness per column.
"""

from collections.abc import Iterable

from glossogen.run_export.agent_identity_columns import agent_identity_cells
from glossogen.run_export.export_run_record import ExportRunRecord
from glossogen.run_export.knob_flattening import knob_cells_by_key
from glossogen.run_export.label_value_columns import label_cells_by_key
from glossogen.run_export.lineage_columns import lineage_cells
from glossogen.run_export.run_metadata_columns import run_metadata_cells


def run_context_cells(record: ExportRunRecord) -> dict[str, str]:
    """Return every non-metric cell for one run, keyed by column name."""
    summary = record.summary
    cells = run_metadata_cells(summary=summary)
    cells.update(knob_cells_by_key(scenario_config=summary.scenario_config))
    cells.update(label_cells_by_key(labels=summary.labels))
    cells.update(agent_identity_cells(agent_models=summary.agent_models))
    cells.update(lineage_cells(summary=summary))
    return cells


def collect_context_keys(records: Iterable[ExportRunRecord]) -> dict[str, int]:
    """Return every available context column and how many runs have a value in it.

    A column counts a run only when that run's cell is non-empty, so the count
    reads as coverage, not as presence of the key.
    """
    coverage: dict[str, int] = {}
    for record in records:
        for key, text in run_context_cells(record=record).items():
            filled = 0
            if text != "":
                filled = 1
            coverage[key] = coverage.get(key, 0) + filled
    return coverage
