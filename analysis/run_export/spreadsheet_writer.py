"""Write a dict of named pandas frames to per-frame CSVs and one multi-sheet workbook."""

import importlib.util
import logging
import re
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# openpyxl rejects ASCII control characters (other than tab \x09, newline \x0a,
# and carriage return \x0d) in cell text. Model output occasionally contains
# such bytes, so they are stripped before writing the workbook.
_ILLEGAL_XLSX_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _strip_illegal_xlsx_chars(value: object) -> object:
    """Remove control characters openpyxl cannot serialize from a string cell."""
    if isinstance(value, str):
        return _ILLEGAL_XLSX_CHARS_RE.sub("", value)
    return value


def _sanitize_frame_for_xlsx(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``frame`` with xlsx-illegal control chars removed from string columns."""
    cleaned = frame.copy()
    for column in cleaned.columns:
        if pd.api.types.is_string_dtype(cleaned[column]):
            cleaned[column] = cleaned[column].map(_strip_illegal_xlsx_chars)
    return cleaned


def write_csvs(frames: dict[str, pd.DataFrame], output_dir: Path, stem: str) -> list[Path]:
    """Write one ``{stem}_{name}.csv`` per frame under ``output_dir``; return written paths."""
    written: list[Path] = []
    for name, frame in frames.items():
        path = output_dir / f"{stem}_{name}.csv"
        frame.to_csv(path, index=False)
        written.append(path)
    return written


def write_xlsx(frames: dict[str, pd.DataFrame], output_dir: Path, stem: str) -> Path | None:
    """Write all frames to one ``{stem}.xlsx`` workbook; return path or ``None`` if no engine."""
    if importlib.util.find_spec("openpyxl") is None:
        logger.warning("openpyxl not importable — skipping .xlsx, CSVs were written.")
        return None
    path = output_dir / f"{stem}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in frames.items():
            _sanitize_frame_for_xlsx(frame=frame).to_excel(writer, sheet_name=name, index=False)
    return path
