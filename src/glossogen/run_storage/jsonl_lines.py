"""Reading and rewriting JSON Lines files one line at a time.

Event logs, debug logs and metric sidecars are all JSONL. Every reader strips each
line, skips the blank ones and parses the rest, and that part lives here. What a
malformed line costs differs between readers: a log that drives evaluation or a
fork must fail on one, a sidecar read across a cohort must not. So the strict and
the tolerant reader are separate, and each caller names the one it means.

Every reader here takes the lines as an iterable of bytes: an open binary file, a tar
member, or ``splitlines()`` of a file read whole. How the file is opened, and
whether it is streamed or read at once, stays with the caller.
"""

from enum import StrEnum
from typing import Any, Callable, Iterable, Iterator, NamedTuple

import orjson


class MalformedLineReason(StrEnum):
    """Why a non-blank line was not a JSON object."""

    NOT_JSON = "not_json"
    NOT_OBJECT = "not_object"


class MalformedLine(NamedTuple):
    """A non-blank line the tolerant reader skipped, and why.

    ``line_number`` counts from 1 and includes blank lines, so it is the line an
    editor shows.
    """

    line_number: int
    text: bytes
    reason: MalformedLineReason


class RewrittenJsonl(NamedTuple):
    """A rewritten file's full contents and how many lines it holds."""

    content: bytes
    line_count: int


def iter_nonblank_lines(lines: Iterable[bytes]) -> Iterator[bytes]:
    """Yield every line of ``lines`` that is not all whitespace, stripped."""
    for line in lines:
        stripped = line.strip()
        if stripped:
            yield stripped


def first_nonblank_line(lines: Iterable[bytes]) -> bytes | None:
    """Return the first line that is not all whitespace, stripped, or ``None`` when there is none.

    Reads no further than that line.
    """
    for line in iter_nonblank_lines(lines=lines):
        return line
    return None


class JsonObjectLines:
    """Strict iteration over a JSONL file's objects, failing on the first line that is not one.

    Iterating yields each non-blank line parsed as a dict. A line that is not JSON
    raises ``orjson.JSONDecodeError``; one that is JSON but not an object raises
    ``TypeError``. ``line_number`` is the line the most recent object came from,
    counted from 1 including blank lines, the way ``csv.reader`` keeps ``line_num``.
    It is an attribute rather than part of each item because the scans of large
    logs read it only to name a line that fails, and building a NamedTuple per
    line measured at about a tenth of the run-summary scan's time.
    """

    def __init__(self, lines: Iterable[bytes]) -> None:
        self._lines = lines
        self.line_number = 0

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for line_number, line in enumerate(self._lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            parsed: Any = orjson.loads(stripped)
            if type(parsed) is not dict:
                raise TypeError(
                    f"line {line_number} is a JSON {type(parsed).__name__}, not an object"
                )
            self.line_number = line_number
            yield parsed


def iter_json_objects_skipping_malformed(
    lines: Iterable[bytes],
    on_malformed: Callable[[MalformedLine], None],
) -> Iterator[dict[str, Any]]:
    """Yield each non-blank line parsed as a dict, passing every other one to ``on_malformed``.

    ``on_malformed`` is called once per skipped line, before the next line is read,
    and decides what a skipped line costs: a count, a log line, or nothing.
    """
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed: Any = orjson.loads(stripped)
        except orjson.JSONDecodeError:
            on_malformed(
                MalformedLine(
                    line_number=line_number,
                    text=stripped,
                    reason=MalformedLineReason.NOT_JSON,
                )
            )
            continue
        if type(parsed) is not dict:
            on_malformed(
                MalformedLine(
                    line_number=line_number,
                    text=stripped,
                    reason=MalformedLineReason.NOT_OBJECT,
                )
            )
            continue
        yield parsed


def rewrite_json_objects(
    lines: Iterable[bytes],
    transform: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> RewrittenJsonl:
    """Parse every line strictly, pass it through ``transform``, and serialize what it returns.

    ``transform`` may edit the record in place and return it, return another one,
    or return ``None`` to drop the line. Blank lines are dropped. The content is
    the kept lines joined by ``\\n`` with one trailing ``\\n``, which is a lone
    ``\\n`` when nothing is kept. Writing it is left to the caller, so a caller
    can refuse the result without having touched the file.
    """
    output_lines: list[bytes] = []
    for record in JsonObjectLines(lines=lines):
        kept = transform(record)
        if kept is None:
            continue
        output_lines.append(orjson.dumps(kept))
    return RewrittenJsonl(content=b"\n".join(output_lines) + b"\n", line_count=len(output_lines))
