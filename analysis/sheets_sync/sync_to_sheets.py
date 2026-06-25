"""Push each analysis exporter's xlsx workbook into its live Google Sheet.

Every exporter writes a multi-sheet workbook under ``analysis/<name>/output/``. This tool reads
that workbook and overwrites the matching **data tabs** in the online spreadsheet, leaving every
other tab (the hand-built charts) untouched. The set of tabs a target may write is a fixed
allowlist (``SyncTarget.data_tabs``) — the tool only ever resolves and clears those worksheets,
so chart tabs are structurally safe.

Safety:

- **Pre-write backup.** Before any real write, the current values of each data tab are snapshotted
  to ``--backup-dir/<target>/<timestamp>/<tab>.csv`` so an overwrite is locally restorable (Google
  Drive also keeps automatic version history on every spreadsheet).
- **Numbers stay numbers, text stays clean.** Frames go to ``set_with_dataframe`` with
  ``value_input_option="USER_ENTERED"``, so numeric cells are written as real numbers at full
  precision and ``NaN`` becomes a blank cell. ``string_escaping="default"`` leaves text cells
  unescaped (no forced-text ``'`` prefix), so columns like ``message_text`` display cleanly.
- **Formatting preserved.** ``clear()`` wipes values only (not number formats); the grid is grown
  to fit but never shrunk, so existing column formatting and any manual extra columns survive.
- **Chunked writes.** Large tabs (message_level runs to ~5M cells) are written in row-slices to
  stay under the per-request size the Sheets API tolerates, each slice retried on transient 5xx.

Auth is a Google service-account key (headless — no browser, no OAuth consent screen): point
``--credentials`` at the key JSON and share each spreadsheet with the service account's email.
"""

import argparse
import csv
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import gspread
import pandas as pd
from gspread.exceptions import APIError, WorksheetNotFound
from gspread_dataframe import set_with_dataframe

logger = logging.getLogger(__name__)

_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
_CONFIG_DIR = Path.home() / ".config" / "schmidt"
_DEFAULT_CREDENTIALS = _CONFIG_DIR / "gcp_service_account.json"
_CREDENTIALS_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON"
_DEFAULT_BACKUP_DIR = Path("analysis/sheets_sync/backups")
# Rows per Sheets write. ~1M cells/request succeeds; the 194k-row message_level tab (~5M
# cells) 500s as one request, so writes are split into slices of this many rows.
_WRITE_CHUNK_ROWS = 25000
_MAX_WRITE_ATTEMPTS = 3


class SyncTarget(NamedTuple):
    """One exporter's workbook and the spreadsheet/tabs it overwrites."""

    name: str
    spreadsheet_id: str
    xlsx: Path
    data_tabs: tuple[str, ...]


# Spreadsheet IDs are link-readable (not secrets). frame-key == tab-name for every target.
_TARGETS: tuple[SyncTarget, ...] = (
    SyncTarget(
        name="baseline",
        spreadsheet_id="1xK3iZaziM7mg5KfIvauN-v3qORKMiT2udSWAWJe7LmE",
        xlsx=Path("analysis/baseline_round_success/output/baseline_round_success.xlsx"),
        data_tabs=("run_level", "message_level", "round_context", "budget_aggregate"),
    ),
    SyncTarget(
        name="channel_noise",
        spreadsheet_id="1iQwlajaQxb9GNRMhxerMZXQl1-eR57xtCo3EfsgsV2M",
        xlsx=Path("analysis/channel_noise_export/output/channel_noise.xlsx"),
        data_tabs=("run_level", "message_level", "round_context", "budget_aggregate"),
    ),
    SyncTarget(
        name="protocol_learnability",
        spreadsheet_id="1AY1z_UUOasvN1Lmow7rj18QysKoW1uOl0K65q7gNiyg",
        xlsx=Path("analysis/protocol_learnability_export/output/protocol_learnability.xlsx"),
        data_tabs=("run_level", "message_level", "baseline_aggregate", "baseline_aggregate_llama"),
    ),
)
_TARGETS_BY_NAME = {target.name: target for target in _TARGETS}


def _build_client(credentials_path: Path) -> gspread.Client:
    """Authenticate with a Google service-account key (headless — no browser, no consent screen)."""
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Service-account key not found at {credentials_path}. In the GCP console create a "
            f"service account and download its JSON key, share each spreadsheet with the service "
            f"account's email (Editor), then set ${_CREDENTIALS_ENV} or pass --credentials. "
            f"See analysis/sheets_sync/README.md."
        )
    return gspread.service_account(filename=str(credentials_path), scopes=[_SHEETS_SCOPE])


def _read_frames(target: SyncTarget) -> dict[str, pd.DataFrame]:
    """Read the workbook's allowlisted sheets into one frame per data tab."""
    if not target.xlsx.exists():
        raise FileNotFoundError(
            f"Workbook {target.xlsx} not found — run the {target.name} exporter first."
        )
    try:
        return pd.read_excel(target.xlsx, sheet_name=list(target.data_tabs))
    except ValueError:
        logger.exception(
            "Workbook %s is missing an expected sheet; re-run the %s exporter.",
            target.xlsx,
            target.name,
        )
        raise


def _backup_target(spreadsheet: gspread.Spreadsheet, target: SyncTarget, backup_dir: Path) -> Path:
    """Snapshot every existing data tab's current values to CSV before overwriting."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = backup_dir / target.name / stamp
    destination.mkdir(parents=True, exist_ok=True)
    for tab in target.data_tabs:
        try:
            worksheet = spreadsheet.worksheet(tab)
        except WorksheetNotFound:
            logger.info("[%s]   no existing %r tab to back up.", target.name, tab)
            continue
        values = worksheet.get_all_values()
        path = destination / f"{tab}.csv"
        with path.open(mode="w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(values)
    return destination


def _ensure_capacity(worksheet: gspread.Worksheet, frame: pd.DataFrame) -> None:
    """Grow the worksheet grid to fit the frame; never shrink (keeps manual columns/formatting)."""
    needed_rows = len(frame) + 1
    needed_cols = max(len(frame.columns), 1)
    new_rows = max(worksheet.row_count, needed_rows)
    new_cols = max(worksheet.col_count, needed_cols)
    if new_rows != worksheet.row_count or new_cols != worksheet.col_count:
        worksheet.resize(rows=new_rows, cols=new_cols)


def _write_chunk(
    worksheet: gspread.Worksheet, frame: pd.DataFrame, start_row: int, include_header: bool
) -> None:
    """Write one row-slice starting at ``start_row``, retrying transient 5xx API errors.

    ``string_escaping="default"`` keeps text cells clean (no forced-text apostrophe prefix);
    numeric cells bypass escaping and are written as real numbers at full precision.
    """
    for attempt in range(1, _MAX_WRITE_ATTEMPTS + 1):
        try:
            set_with_dataframe(
                worksheet=worksheet,
                dataframe=frame,
                row=start_row,
                include_index=False,
                include_column_header=include_header,
                resize=False,
                string_escaping="default",
            )
            return
        except APIError:
            if attempt == _MAX_WRITE_ATTEMPTS:
                raise
            logger.warning(
                "write at row %d failed (attempt %d/%d); retrying.",
                start_row,
                attempt,
                _MAX_WRITE_ATTEMPTS,
            )
            time.sleep(2 * attempt)


def _write_tab(worksheet: gspread.Worksheet, frame: pd.DataFrame) -> None:
    """Clear the tab's values (formats kept) and write the frame in row-chunks.

    Large single writes (the message_level tabs run to ~5M cells) make the Sheets API return
    500s, so the frame is written in ``_WRITE_CHUNK_ROWS``-row slices: the first carries the
    header at row 1, each later slice lands at ``2 + rows_already_written``.
    """
    _ensure_capacity(worksheet=worksheet, frame=frame)
    worksheet.clear()
    _write_chunk(
        worksheet=worksheet,
        frame=frame.iloc[:_WRITE_CHUNK_ROWS],
        start_row=1,
        include_header=True,
    )
    written = _WRITE_CHUNK_ROWS
    while written < len(frame):
        _write_chunk(
            worksheet=worksheet,
            frame=frame.iloc[written : written + _WRITE_CHUNK_ROWS],
            start_row=2 + written,
            include_header=False,
        )
        written += _WRITE_CHUNK_ROWS


def _resolve_worksheet(
    spreadsheet: gspread.Spreadsheet, tab: str, frame: pd.DataFrame
) -> gspread.Worksheet:
    """Return the named worksheet, creating it sized to the frame if it does not exist yet."""
    try:
        return spreadsheet.worksheet(tab)
    except WorksheetNotFound:
        return spreadsheet.add_worksheet(
            title=tab, rows=len(frame) + 1, cols=max(len(frame.columns), 1)
        )


def _sync_target(
    client: gspread.Client, target: SyncTarget, backup_dir: Path, dry_run: bool
) -> None:
    """Sync one target's data tabs, or report the plan when ``dry_run`` is set."""
    frames = _read_frames(target=target)
    try:
        spreadsheet = client.open_by_key(target.spreadsheet_id)
        existing = {worksheet.title for worksheet in spreadsheet.worksheets()}
    except (APIError, PermissionError):
        logger.exception(
            "[%s] cannot open spreadsheet %s. Confirm the Google Sheets API is enabled in the "
            "service account's project and the spreadsheet is shared with the service account's "
            "email (Editor).",
            target.name,
            target.spreadsheet_id,
        )
        raise
    logger.info(
        "[%s] %s — existing tabs: %s", target.name, spreadsheet.title, ", ".join(sorted(existing))
    )

    for tab in target.data_tabs:
        frame = frames[tab]
        action = "update" if tab in existing else "create"
        suffix = " (dry-run)" if dry_run else ""
        logger.info(
            "[%s]   %s %r: %d rows x %d cols%s",
            target.name,
            action,
            tab,
            len(frame),
            len(frame.columns),
            suffix,
        )
    if dry_run:
        return

    backup_path = _backup_target(spreadsheet=spreadsheet, target=target, backup_dir=backup_dir)
    logger.info("[%s] backed up current tabs to %s", target.name, backup_path)
    for tab in target.data_tabs:
        worksheet = _resolve_worksheet(spreadsheet=spreadsheet, tab=tab, frame=frames[tab])
        _write_tab(worksheet=worksheet, frame=frames[tab])
    logger.info("[%s] done — %d data tabs written.", target.name, len(target.data_tabs))


def _selected_targets(target_arg: str) -> list[SyncTarget]:
    """Resolve the ``--target`` flag to the list of targets to sync."""
    if target_arg == "all":
        return list(_TARGETS)
    return [_TARGETS_BY_NAME[target_arg]]


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=[*sorted(_TARGETS_BY_NAME), "all"],
        default="all",
        help="Which exporter's workbook to push (default: all).",
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=Path(os.environ.get(_CREDENTIALS_ENV, str(_DEFAULT_CREDENTIALS))),
        help=f"Service-account key JSON (default ${_CREDENTIALS_ENV} or {_DEFAULT_CREDENTIALS}).",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=_DEFAULT_BACKUP_DIR,
        help=f"Where pre-write tab snapshots are written (default {_DEFAULT_BACKUP_DIR}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List current tabs and planned writes without modifying the spreadsheet.",
    )
    return parser.parse_args()


def main() -> None:
    """Authenticate once, then sync (or dry-run) each selected target."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    targets = _selected_targets(target_arg=args.target)
    client = _build_client(credentials_path=args.credentials)
    for target in targets:
        _sync_target(client=client, target=target, backup_dir=args.backup_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
