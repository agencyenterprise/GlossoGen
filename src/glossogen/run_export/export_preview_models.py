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

    ``rounds_reported`` is how many round observations this metric carries across
    the selection. It is not a row count: every metric is a column, so metrics
    share the rows they fall on. The largest of them is what a caller estimates
    the round table's height from, since one metric's rounds are usually a subset
    of another's rather than disjoint.

    There is no per-metric agent count. The agent table is keyed on the run's
    registered roster, so its height is ``agent_row_count`` on the selection and
    no choice of metrics moves it.
    """

    metric_name: str
    label: str
    score_unit: str
    runs_with_value: int
    rounds_reported: int


class MultiRunExportPreview(BaseModel):
    """Everything a client needs to describe an export before requesting it.

    ``raw_bytes_estimate`` is the on-disk size of the run folders a raw export
    would carry, and is ``None`` when it was not asked for. ``missing_run_ids``
    lists explicitly named ids that no longer resolve to a run this group owns.

    ``agent_row_count`` and ``message_row_count`` are what the agent and message
    tables would hold. Both are run-level totals rather than per-metric ones: an
    agent row is an agent and a message row is a message, so no choice of metrics
    changes either. The agent count is the registered roster, which is what that
    table is keyed on.

    ``injection_row_estimate`` is rounds times roster, which is the shape of a
    scenario that briefs every agent every round. It is an estimate and named
    one, because the true count is in the event logs and the preview does not
    open them.
    """

    run_count: int
    run_ids: list[str]
    scenario_names: list[str]
    evaluated_run_count: int
    in_progress_run_count: int
    runs_without_report: list[str]
    missing_run_ids: list[str]
    raw_bytes_estimate: int | None
    agent_row_count: int
    message_row_count: int
    injection_row_estimate: int
    columns: list[ExportValueColumn]
    metrics: list[ExportMetricColumn]
    max_run_count: int
    max_raw_bytes: int
    max_csv_bytes: int
