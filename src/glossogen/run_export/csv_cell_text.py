"""Turning a Python value into one CSV cell.

Two problems this solves, both of which come from the cells carrying model output.

Control characters. Agent messages and judge summaries contain them, and a
spreadsheet refuses a file that does. Stripping beats escaping here: none of them
mean anything in a data frame.

Embedded newlines. A newline inside a quoted field is legal CSV, and the
line-oriented tools people reach for first do not read it that way: `wc -l`
overcounts, `head` truncates mid-record, and a naive split lands half a row in the
next record. Every field that can contain one holds prose, where a space loses
nothing.

Leading characters a spreadsheet reads as a formula. A judge note really does
begin `@ notation established: '@B' means ...`, and Excel renders a cell starting
with `@` as `#NAME?`, losing the note without saying so. Such cells are prefixed
with an apostrophe, which Excel treats as "this is text" and does not display.

`-` is deliberately not guarded: a leading minus is far more often a negative
number than a formula, and numbers do not pass through the text path anyway.

Floats keep their full repr. Rounding to a fixed number of decimals here would
silently discard precision a metric computed.
"""

import re
from datetime import datetime
from typing import Any, cast

import orjson

# C0 minus tab, plus DEL and C1. Tab survives because it is a legal cell
# character that `csv` quotes correctly.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

_NEWLINE_RE = re.compile(r"\r\n|\r|\n")

MULTI_VALUE_SEPARATOR = "; "

# `-` is absent on purpose: see the module docstring.
_FORMULA_LEAD_CHARS = ("=", "+", "@", "\t")


def guard_spreadsheet_formula(text: str) -> str:
    """Prefix an apostrophe when a spreadsheet would read the cell as a formula."""
    if text.startswith(_FORMULA_LEAD_CHARS):
        return f"'{text}"
    return text


def sanitize_cell_text(text: str) -> str:
    """Strip control characters and flatten newlines to single spaces."""
    without_newlines = _NEWLINE_RE.sub(" ", text)
    return _CONTROL_CHARS_RE.sub("", without_newlines)


def render_cell(text: str) -> str:
    """Render a finished text cell: sanitized, then guarded against formula reading.

    Applied once per cell, not per fragment: only the first character
    of the whole cell decides how a spreadsheet reads it.
    """
    return guard_spreadsheet_formula(text=sanitize_cell_text(text=text))


def render_scalar(value: Any) -> str:
    """Render one knob, metric, or metadata value as cell text.

    Mappings and sequences become compact JSON with sorted keys, so a cell that
    cannot be a column stays machine-readable instead of becoming a Python repr.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        if value:
            return "True"
        return "False"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return render_cell(text=value)
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return render_json(value=value)
    return render_cell(text=str(value))


def render_json(value: Any) -> str:
    """Render a container as compact JSON with sorted keys."""
    if isinstance(value, (set, frozenset)):
        # A JSON round trip cannot represent a set, and its iteration order is
        # not stable across processes, so it is sorted into a list first.
        return render_json(value=sorted(cast(frozenset[Any], value), key=str))
    raw = orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")
    return sanitize_cell_text(text=raw)


def render_string_list(values: list[str]) -> str:
    """Join multi-value cells with a separator that does not fight the format.

    A comma would need the whole cell quoted and still reads as a column break to
    anyone eyeballing the file.
    """
    joined = MULTI_VALUE_SEPARATOR.join(sanitize_cell_text(text=value) for value in values)
    return guard_spreadsheet_formula(text=joined)
