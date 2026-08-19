"""Writing one frame as CSV bytes into an open binary stream.

UTF-8 with no byte-order mark. A BOM makes Excel guess the encoding correctly on
a double-click, and it also leaves a stray character glued to the first column's
name when the file is read by the default settings of every data-frame library.
The second cost is worse: it corrupts an analysis, where the first only spoils a
preview.

`\\n` line endings, not the `\\r\\n` the CSV spec asks for, so the same selection
exports the same bytes on every platform. Everything that reads CSV accepts both.

Rows are encoded one at a time through a reused buffer. Wrapping the destination in
a `TextIOWrapper` would buffer writes out of the caller's sight, and the caller is
watching how far the destination has grown. Encoding here also leaves the destination
as anything with a `write`: a file, a `BytesIO`, or an open zip entry.
"""

import csv
import io
from collections.abc import Callable
from typing import IO

from glossogen.run_export.csv_frame import CsvFrame

# Checking on every row would stat the destination hundreds of thousands of
# times; a few hundred rows of overshoot past the ceiling costs nothing.
_CHECK_EVERY_ROWS = 500


def write_frame(
    frame: CsvFrame,
    destination: IO[bytes],
    check: Callable[[], None] | None,
) -> tuple[int, int]:
    """Write ``frame`` as CSV and return its row count and byte count.

    Rows are consumed one at a time, so a frame with hundreds of thousands of rows
    never accumulates in memory.

    ``check`` is called every few hundred rows and once at the end, and is expected
    to raise if the export has grown too large. It takes no argument because the
    caller decides what to measure: the byte count returned here is uncompressed,
    which is not what a zip delivers.
    """
    line = io.StringIO(newline="")
    writer = csv.writer(line, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)

    def emit(row: list[str]) -> int:
        """Encode one row and write it, returning the bytes written."""
        line.seek(0)
        line.truncate(0)
        writer.writerow(row)
        data = line.getvalue().encode("utf-8")
        destination.write(data)
        return len(data)

    written = emit(list(frame.header))
    row_count = 0
    for row in frame.rows:
        written += emit(row)
        row_count += 1
        if check is not None and row_count % _CHECK_EVERY_ROWS == 0:
            check()
    if check is not None:
        check()
    return (row_count, written)
