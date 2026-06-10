"""Write a dict of named pandas frames to per-frame CSVs and one multi-sheet workbook."""

import importlib.util
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


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
            frame.to_excel(writer, sheet_name=name, index=False)
    return path
