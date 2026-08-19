"""Labels as columns: `key=value` split into a value, a bare tag into a flag.

Cohorts encode their conditions in labels: a sweep over a time budget tags its
runs `budget=250`, `budget=450`, and so on. In a CSV those want to be a `budget`
column holding `250`, not a substring of a joined label cell that has to be
parsed again in R.

The conditions that are not `key=value` want a column just as much. A run is
tagged `baseline_oss` or `random_seed` or it is not, and that is the grouping
variable for a whole cohort. Without a column, filtering on one means
substring-matching the joined `labels` cell, which is the thing this repository
learned not to do the hard way: `"baseline" in labels_text` also matches
`baseline_oss`, and matching on the joined cell once destroyed the eval-derived
labels of 40 runs.

So a bare tag becomes `label_flag.<tag>` holding `True`. The prefix is separate
from `label.` because a cohort can carry both `budget` and `budget=800`, and
merging them would put a flag and a value in one column.

A run that does not carry the tag has an empty cell rather than `False`. The
column set is the union across the selection, and a run's own labels are read
without knowing which tags the other runs carry. Empty therefore means the run is
not tagged, which for labels is knowable and total: `labels.json` lists every tag
a run has. The legend's coverage count reads as how many runs carry the tag.

A duplicate key keeps the first label in sorted order, so the cell is the same
whatever order the labels were written in. That case means the run was tagged
inconsistently, and picking deterministically beats picking arbitrarily.
"""

from glossogen.run_export.csv_cell_text import render_cell, sanitize_cell_text

LABEL_COLUMN_PREFIX = "label."
LABEL_FLAG_COLUMN_PREFIX = "label_flag."

_PRESENT = "True"


def label_cells_by_key(labels: list[str]) -> dict[str, str]:
    """Return the label columns a run's labels contribute, values and flags alike."""
    cells: dict[str, str] = {}
    for label in sorted(labels):
        key, separator, value = label.partition("=")
        if not key:
            continue
        if not separator:
            cells.setdefault(f"{LABEL_FLAG_COLUMN_PREFIX}{sanitize_cell_text(text=key)}", _PRESENT)
            continue
        column = f"{LABEL_COLUMN_PREFIX}{sanitize_cell_text(text=key)}"
        if column in cells:
            continue
        cells[column] = render_cell(text=value)
    return cells
