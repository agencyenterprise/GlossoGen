"""What a selection would produce, described before anything is built.

The preview is computed from the same records the export itself reads, so the
columns it offers are exactly the columns the export can fill. There is no static
column list anywhere that could drift from the data.

Per-column coverage counts are what make a mixed-scenario export readable. A knob
only one of two scenarios defines is blank on the other's rows. A caller that knows
the column is filled in 8 of 128 runs can say so, and the reader stops wondering
whether the blanks are a bug.

All three ceilings are reported here, so a caller renders the limit the endpoint
actually enforces instead of its own copy. Only the raw one comes with an estimate to
compare against: CSV bytes are counted during the write and never predicted,
so a caller can state that ceiling but not tell in advance whether a request will
reach it.
"""

from pydantic import BaseModel


class ExportValueColumn(BaseModel):
    """One run-context column an export can carry.

    ``group`` is which family it came from, used to lay out a column picker.
    ``runs_with_value`` is how many runs in the selection have a non-empty cell.
    ``always_included`` marks the identity columns, which every frame emits.
    """

    key: str
    label: str
    group: str
    runs_with_value: int
    always_included: bool


class ExportMetricColumn(BaseModel):
    """One evaluator metric an export can carry.

    ``round_row_count`` and ``agent_row_count`` are the rows this metric would
    contribute to the long tables, so a caller can total the metrics it picked
    without asking again.
    """

    metric_name: str
    label: str
    score_unit: str
    runs_with_value: int
    round_row_count: int
    agent_row_count: int


class MultiRunExportPreview(BaseModel):
    """Everything a client needs to describe an export before requesting it.

    ``raw_bytes_estimate`` is the on-disk size of the run folders a raw export
    would carry, and is ``None`` when it was not asked for. ``missing_run_ids``
    lists explicitly named ids that no longer resolve to a run this group owns.
    """

    run_count: int
    run_ids: list[str]
    scenario_names: list[str]
    evaluated_run_count: int
    in_progress_run_count: int
    runs_without_report: list[str]
    missing_run_ids: list[str]
    raw_bytes_estimate: int | None
    columns: list[ExportValueColumn]
    metrics: list[ExportMetricColumn]
    max_run_count: int
    max_raw_bytes: int
    max_csv_bytes: int
