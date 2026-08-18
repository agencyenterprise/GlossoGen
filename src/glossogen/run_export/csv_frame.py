"""One CSV table, as a header plus a lazy stream of rows.

Rows are an iterator, not a list, because the long frames are large: a
few hundred runs times a few dozen metrics times the rounds each scored reaches
hundreds of thousands of rows. Held as a list they would sit in memory next to
the archive being written; streamed into an open zip entry they never accumulate.
"""

from collections.abc import Iterator
from typing import NamedTuple


class CsvFrame(NamedTuple):
    """A named CSV table: its column names and its rows, in order."""

    name: str
    header: list[str]
    rows: Iterator[list[str]]
