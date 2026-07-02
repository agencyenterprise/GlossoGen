# Google Sheets sync

Pushes each analysis exporter's generated workbook into its live Google Sheet, so a re-export no
longer needs manual copy-paste. The tool overwrites **only the data tabs** of each spreadsheet and
never touches the chart/plot tabs.

## What it syncs

| `--target` | Workbook | Spreadsheet | Data tabs overwritten |
|---|---|---|---|
| `baseline` | `analysis/baseline_round_success/output/baseline_round_success.xlsx` | [`1xK3i…7LmE`](https://docs.google.com/spreadsheets/d/1xK3iZaziM7mg5KfIvauN-v3qORKMiT2udSWAWJe7LmE) | `run_level`, `message_level`, `round_context`, `budget_aggregate` |
| `channel_noise` | `analysis/channel_noise_export/output/channel_noise.xlsx` | [`1iQwl…V2M`](https://docs.google.com/spreadsheets/d/1iQwlajaQxb9GNRMhxerMZXQl1-eR57xtCo3EfsgsV2M) | `run_level`, `message_level`, `round_context`, `budget_aggregate` |
| `drive_module_repair` | `analysis/baseline_round_success/output/drive_module_repair_baseline.xlsx` | [`105fG…kOnY`](https://docs.google.com/spreadsheets/d/105fG5BbWi8UsS7CO6Kb0YRDaMO5Ff-wLbhS71qjkOnY) | `run_level`, `message_level`, `round_context`, `budget_aggregate` |
| `protocol_learnability` | `analysis/protocol_learnability_export/output/protocol_learnability.xlsx` | [`1AY1z…Niyg`](https://docs.google.com/spreadsheets/d/1AY1z_UUOasvN1Lmow7rj18QysKoW1uOl0K65q7gNiyg) | `run_level`, `message_level`, `baseline_aggregate`, `baseline_aggregate_llama` |
| `spot_the_difference` | `analysis/spot_the_difference_export/output/spot_the_difference.xlsx` | [`1x1F0…zKiI`](https://docs.google.com/spreadsheets/d/1x1F0YPsztudX1YwDeWJ-yMp6s3h9uHUBIGzWS79zKiI) | `run_level`, `round_level`, `message_level`, `team_aggregate` |

The workbook sheet name maps 1:1 to the spreadsheet tab name. Any tab not in the list above (the
hand-built charts) is never resolved, cleared, or written.

The `spot_the_difference` spreadsheet's chart tabs (`Plot: *`) are (re)built by a separate,
idempotent tool — `analysis/spot_the_difference_export/build_spot_charts.py` (`make charts-spot`) —
which the data sync above never touches.

## Safety

- **Only the allowlisted data tabs are touched.** The tool resolves worksheets strictly by the names
  in `SyncTarget.data_tabs`; there is no spreadsheet-wide clear and no worksheet deletion, so chart
  tabs are structurally safe.
- **Pre-write backup.** Before any real write, each existing data tab's current values are snapshotted
  to `--backup-dir/<target>/<timestamp>/<tab>.csv` (default `analysis/sheets_sync/backups/`, gitignored).
  Google Drive also keeps automatic version history on every spreadsheet (**File → Version history**),
  so any overwrite is revertible there too.
- **Numbers stay numbers, text stays clean.** Frames are written with
  `value_input_option="USER_ENTERED"`, so numeric cells go in as real numbers at full precision and
  `NaN` becomes a blank cell. `string_escaping="default"` leaves text cells unescaped (no forced-text
  `'` prefix), so columns like `message_text` display exactly as written.
- **Chunked writes.** Large tabs (`message_level` runs to ~5M cells) are written in row-slices so a
  single request never exceeds the size the Sheets API tolerates; each slice is retried on transient
  5xx errors.
- **Formatting preserved.** Writes use `clear()` (which wipes values only, not number formats) and grow
  the tab's grid to fit but never shrink it, so existing column number-formats and any manual extra
  columns survive a sync.

## One-time setup (service account)

A service account is a headless robot identity — no browser, no OAuth consent screen. Setup is once:

1. In the [Google Cloud console](https://console.cloud.google.com/), create (or pick) a project and
   **enable the Google Sheets API**.
2. **APIs & Services → Credentials → Create credentials → Service account.** Create it, then on its
   **Keys** tab choose **Add key → Create new key → JSON** and download the key file.
3. Save the key to `~/.config/schmidt/gcp_service_account.json` (or set `GOOGLE_SERVICE_ACCOUNT_JSON` /
   pass `--credentials`).
4. **Share each of the three spreadsheets with the service account's email** (the `client_email` field
   in the key JSON, e.g. `…@<project>.iam.gserviceaccount.com`) as **Editor**. That share is what grants
   write access — the robot can only touch sheets you've explicitly shared with it.

The scope requested is `https://www.googleapis.com/auth/spreadsheets` (read/write to sheets shared with
the service account — no Drive-wide access).

> If your Google Workspace org blocks service-account key downloads (the
> `iam.disableServiceAccountKeyCreation` policy), step 2 is disabled — say so and the tool can switch to
> a browser-based OAuth flow instead.

## Usage

Always regenerate the workbook first, then sync. Run from the repo root.

```bash
# Dry run — authenticate, list each spreadsheet's current tabs, and report planned writes. No changes.
VIRTUAL_ENV= PYTHONPATH=. uv run --group sheets --no-sync \
  python analysis/sheets_sync/sync_to_sheets.py --target all --dry-run

# Real sync of one target (backs up first).
VIRTUAL_ENV= PYTHONPATH=. uv run --group sheets --no-sync \
  python analysis/sheets_sync/sync_to_sheets.py --target baseline
```

`--target` is one of `baseline`, `channel_noise`, `drive_module_repair`, `protocol_learnability`,
`spot_the_difference`, or `all` (default).

### Makefile shortcuts (export + sync in one command)

```bash
make sync-sheets-baseline   # regenerate the baseline workbook, then push it
make sync-sheets-noise      # channel-noise
make sync-sheets-protocol   # protocol-learnability (merged frontier + llama)
make sync-sheets-spot       # spot_the_difference (data tabs only)
make sync-sheets            # all of the above
```

### spot_the_difference chart tabs

The spot spreadsheet's hand-authored `Plot: *` chart tabs are rebuilt separately (the data sync
never touches them):

```bash
make charts-spot            # (re)build every Plot: * tab + its embedded chart, idempotently
```

