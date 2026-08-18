"""Ceilings on how much one export may cover, and the error raised past them.

Three different things are bounded here, so there are three numbers.

The **run count** bounds how long a synchronous request runs. Cohorts here reach
several thousand runs, and the largest labelled one is around 3,600, so a ceiling
below that refuses the work people actually do. Measured: 1,200 runs export in about
twelve seconds and 3,580 in about thirteen, because the cost is dominated by the
directory scan and not by per-run work. This sits where the request still returns
inside a proxy timeout, not where the data stops being interesting.

The **raw byte** ceiling is estimated up front by sizing the run folders, and it
counts them uncompressed. The zip a client receives is smaller: measured across three
scenarios here, 5.7x to 7.0x smaller. So this ceiling is conservative, and 4 GiB
counted is around 600 MiB delivered. Sizing first is what makes the refusal cheap,
since nothing has to be compressed to find out.

The **CSV byte** ceiling bounds the same delivery for the tables, and it counts what
the client receives: compressed inside a zip, raw for a bare CSV. Counting the rows'
own bytes would hold the two shapes to ceilings differing by the compression ratio,
and CSV deflates by two orders of magnitude.

It is counted during the write, not estimated beforehand. Row count is a poor
stand-in, because the long tables repeat the run columns onto every row by default
and repetition is exactly what deflate removes: turning it off cut one cohort's
uncompressed bytes sixfold and its delivered bytes by about a fifth. Counting is
exact, and the archive is fully built before a byte of it is sent, so stopping partway
costs only the temporary file.

A single CSV is the one shape where counted equals delivered, so this number is the
size it really permits there. One cohort's round-level table alone reaches 273 MiB,
which is a large object for a browser tab to hold, and that is what the setting buys.

The CSV ceiling applies to the HTTP path only, since `glossogen export` writes to a
directory and nothing holds a table in memory. The raw ceiling does apply to the CLI:
`--raw` goes through the same writer, and the command turns a breach into a clean
exit.
"""

MAX_EXPORT_RUN_COUNT: int = 5000

MAX_RAW_EXPORT_BYTES: int = 4 * 1024 * 1024 * 1024

MAX_CSV_EXPORT_BYTES: int = 512 * 1024 * 1024


class ExportTooLargeError(Exception):
    """A selection exceeds one of the export ceilings.

    Carries the message a caller is shown, so the limit is stated once here and not
    reworded at each surface.
    """


def _gibibytes(count: int) -> str:
    """Render a byte count in GiB, to one decimal."""
    return f"{count / (1024 * 1024 * 1024):.1f} GiB"


def _mebibytes(count: int) -> str:
    """Render a byte count in MiB, to the nearest whole one."""
    return f"{count / (1024 * 1024):.0f} MiB"


def check_run_count(run_count: int) -> None:
    """Raise :class:`ExportTooLargeError` if ``run_count`` is over the ceiling."""
    if run_count > MAX_EXPORT_RUN_COUNT:
        raise ExportTooLargeError(
            f"This selection is {run_count} runs. The limit is {MAX_EXPORT_RUN_COUNT}. "
            "Narrow the filters, select fewer runs, or use the glossogen export command."
        )


def check_raw_bytes(total_bytes: int) -> None:
    """Raise :class:`ExportTooLargeError` if ``total_bytes`` is over the ceiling."""
    if total_bytes > MAX_RAW_EXPORT_BYTES:
        raise ExportTooLargeError(
            f"These run folders total {_gibibytes(total_bytes)}. The limit is "
            f"{_gibibytes(MAX_RAW_EXPORT_BYTES)}. Narrow the filters or select fewer runs."
        )


def check_csv_bytes(total_bytes: int) -> None:
    """Raise :class:`ExportTooLargeError` if the tables written are over the ceiling."""
    if total_bytes > MAX_CSV_EXPORT_BYTES:
        raise ExportTooLargeError(
            f"These tables exceed {_mebibytes(MAX_CSV_EXPORT_BYTES)} to download. Select "
            "fewer runs, drop the long tables, or use the glossogen export command, which "
            "writes to a directory and has no such limit."
        )
