"""Shared Google Sheets service-account client construction.

Used by both the data-sync tool (``sync_to_sheets.py``) and the spot chart
builder (``build_spot_charts.py``). A service account is a headless robot
identity — no browser, no OAuth consent screen; the key is shared with each
target spreadsheet as an Editor.
"""

import os
from pathlib import Path

import gspread

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
_CONFIG_DIR = Path.home() / ".config" / "glossogen"
DEFAULT_CREDENTIALS = _CONFIG_DIR / "gcp_service_account.json"
CREDENTIALS_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON"


def default_credentials_path() -> Path:
    """Resolve the service-account key path from ``$GOOGLE_SERVICE_ACCOUNT_JSON`` or the default."""
    return Path(os.environ.get(CREDENTIALS_ENV, str(DEFAULT_CREDENTIALS)))


def build_sheets_client(credentials_path: Path) -> gspread.Client:
    """Authenticate with a Google service-account key (headless — no browser, no consent screen)."""
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"Service-account key not found at {credentials_path}. In the GCP console create a "
            f"service account and download its JSON key, share each spreadsheet with the service "
            f"account's email (Editor), then set ${CREDENTIALS_ENV} or pass --credentials. "
            f"See analysis/sheets_sync/README.md."
        )
    return gspread.service_account(filename=str(credentials_path), scopes=[SHEETS_SCOPE])
