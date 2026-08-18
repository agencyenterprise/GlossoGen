"""Labels shaped like `key=value`, split into their own columns.

Cohorts encode their conditions in labels: a sweep over a time budget tags its
runs `budget=250`, `budget=450`, and so on. In a CSV those want to be a `budget`
column holding `250`, not a substring of a joined label cell that has to be
parsed again in R.

Labels with no `=` stay in the joined `labels` column and contribute no column of
their own. A plain tag like `baseline_oss` has no value to put in a cell.

A duplicate key keeps the first label in sorted order, so the cell is the same
whatever order the labels were written in. That case means the run was tagged
inconsistently, and picking deterministically beats picking arbitrarily.
"""

from glossogen.run_export.csv_cell_text import render_cell, sanitize_cell_text

LABEL_COLUMN_PREFIX = "label."


def label_cells_by_key(labels: list[str]) -> dict[str, str]:
    """Return the ``label.<key>`` cells the ``key=value`` labels contribute."""
    cells: dict[str, str] = {}
    for label in sorted(labels):
        key, separator, value = label.partition("=")
        if not separator:
            continue
        if not key:
            continue
        column = f"{LABEL_COLUMN_PREFIX}{sanitize_cell_text(text=key)}"
        if column in cells:
            continue
        cells[column] = render_cell(text=value)
    return cells
