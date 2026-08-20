"""Rendering an analysis result as aligned text for a terminal.

Every row carries how many runs and how many observations it aggregated, and every
measure carries its own ``n``. A measure's ``n`` can be lower than the row's
observation count, which is what a metric that did not report on some of them looks
like, and the point of printing both.

A value that could not be computed prints as ``-``, never as ``0``.
"""

from glossogen.run_analysis.analysis_result_models import AnalysisFieldCatalog, AnalysisResult

MISSING_CELL = "-"

# What the single row of an ungrouped query is called. The chart, the web table, the
# CSV and this table all render that row, and each had picked its own word for it.
UNGROUPED_LABEL = "All runs"


def _format_value(value: float | None) -> str:
    """Render one aggregate, or a dash when there is no number."""
    if value is None:
        return MISSING_CELL
    return f"{value:.4g}"


def result_header(result: AnalysisResult) -> list[str]:
    """Return the table's column names."""
    header = list(result.group_by)
    if not header:
        header = ["group"]
    header.extend(["runs", "obs"])
    for measure in result.measures:
        header.extend([measure.column_key, "n"])
    return header


def result_rows(result: AnalysisResult) -> list[list[str]]:
    """Return the table's rows as text."""
    rows: list[list[str]] = []
    for row in result.rows:
        cells = list(row.group_values)
        if not result.group_by:
            cells = [UNGROUPED_LABEL]
        observations = 0
        if row.cells:
            observations = row.cells[0].observation_count + row.cells[0].missing_count
        cells.extend([str(row.run_count), str(observations)])
        for cell in row.cells:
            cells.extend([_format_value(value=cell.value), str(cell.observation_count)])
        rows.append(cells)
    return rows


def render_text_table(result: AnalysisResult) -> str:
    """Render the whole result as one aligned table."""
    header = result_header(result=result)
    rows = result_rows(result=result)
    widths = [len(name) for name in header]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    lines = [
        "  ".join(name.ljust(widths[index]) for index, name in enumerate(header)),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)) for row in rows
    )
    return "\n".join(lines)


def render_field_catalog(catalog: AnalysisFieldCatalog) -> str:
    """Render the dimensions and measures a selection carries, for a terminal.

    Dimensions print with how many distinct values they take, because that is what
    decides whether one is worth grouping on: two values make a comparison and four
    hundred make a list.
    """
    lines = [
        f"{catalog.run_count} runs, {catalog.observation_count} "
        f"{catalog.grain.value} observations",
    ]
    if catalog.runs_without_report:
        lines.append(f"{len(catalog.runs_without_report)} of them have no evaluation report")

    lines.append("")
    lines.append("dimensions (group by / filter on)")
    for dimension in catalog.dimensions:
        sample = ", ".join(value.value for value in dimension.values[:4])
        lines.append(
            f"  {dimension.key}  [{dimension.group}]  "
            f"{dimension.distinct_count} distinct, {dimension.rows_with_value} filled"
            f"  e.g. {sample}"
        )

    lines.append("")
    lines.append("measures (--measure key:aggregate)")
    for measure in catalog.measures:
        lines.append(
            f"  {measure.source}:{measure.key}  {measure.rows_with_value} rows"
            f"  unit: {measure.score_unit}"
        )
    return "\n".join(lines)
