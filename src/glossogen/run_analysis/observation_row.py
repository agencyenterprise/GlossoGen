"""One observation: what it can be sliced by, and what it measured.

Dimensions are text and measures are numbers. A dimension cell is the same string the
CSV export would write, so a chart grouped on a knob and a spreadsheet filtered on it
agree on what the values are.

A measure is ``None`` when no number exists, and that is never rendered as zero.
"""

from typing import NamedTuple


class ObservationRow(NamedTuple):
    """A run, round, or agent, with its dimension cells and its measured values."""

    run_id: str
    dimensions: dict[str, str]
    measures: dict[str, float | None]
