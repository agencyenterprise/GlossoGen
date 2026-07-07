"""(Re)build the hand-authored chart tabs in the spot_the_difference spreadsheet.

The data sync (``analysis/sheets_sync/sync_to_sheets.py``) only ever writes the
five data tabs and never touches chart tabs. This tool owns the ``Plot: *`` tabs:
it recomputes the small aggregate tables each chart reads from the exported
workbook, writes one helper tab per plot, and embeds the charts via the Sheets
API. It is idempotent — every ``Plot: *`` tab is deleted and rebuilt on each run,
so re-running after a data refresh regenerates clean charts.

The plot set mirrors the veyru baseline spreadsheet's intent, adapted to
spot_the_difference's two-team design:

- ``Plot: Model Performance`` — COLUMN chart of per-model mean round-success
  fraction (correctness gate), win fraction (fewest-characters competitive win),
  and mean found fraction (partial credit).
- ``Plot: Round by Round`` — three LINE charts (per-model mean success, mean
  characters used, and mean perplexity by round number).
- ``Plot: Perplexity vs Success`` — SCATTER of per-(run, team) perplexity against
  round-success fraction, one series per model.
- ``Plot: Characters per Model`` — COLUMN chart of per-model mean link characters
  used per round (spot's efficiency headline: the fewest-characters team wins).

Per-team / head-to-head plots (does communication behaviour predict the winner?):

- ``Plot: Perplexity vs Wins`` — SCATTER of per-(run, team) perplexity against the
  team's win fraction, one series per model.
- ``Plot: Winner vs Loser by Model`` — two COLUMN charts comparing the mean
  perplexity and mean repetition of the winning vs losing team, per model, over
  every decided round (a round with exactly one winner).
- ``Plot: Winner vs Loser Perplexity`` — SCATTER of the winning team's perplexity
  (x) against the losing team's perplexity (y) for each decided round; points below
  the ``y = x`` diagonal are rounds the lower-perplexity team won.
"""

import argparse
import logging
from pathlib import Path
from typing import NamedTuple

import gspread
import pandas as pd
from gspread_dataframe import set_with_dataframe

from analysis.sheets_sync.sheets_client import (
    CREDENTIALS_ENV,
    build_sheets_client,
    default_credentials_path,
)

logger = logging.getLogger(__name__)

SPREADSHEET_ID = "1x1F0YPsztudX1YwDeWJ-yMp6s3h9uHUBIGzWS79zKiI"
_XLSX = Path("analysis/spot_the_difference_export/output/spot_the_difference.xlsx")
_PLOT_PREFIX = "Plot: "
_CHART_WIDTH_PX = 640
_CHART_HEIGHT_PX = 400
_CHART_ROW_STRIDE = 22


class ChartSpec(NamedTuple):
    """One embedded chart on a plot tab: its type and the helper-table columns it reads.

    Column indices are 0-based into the tab's helper table. ``domain_col`` is the
    x-axis category/value column; ``series_cols`` are the y-series columns (each
    column's header row supplies the series name).
    """

    title: str
    chart_type: str
    domain_col: int
    series_cols: tuple[int, ...]
    x_title: str
    y_title: str


class PlotSpec(NamedTuple):
    """One plot tab: its title, the helper table to write, and the charts to embed."""

    tab_title: str
    frame: pd.DataFrame
    charts: tuple[ChartSpec, ...]


def _model_label(viewer_left_model: str, viewer_right_model: str) -> str:
    """Return the team's model label: the shared model, or ``left|right`` when they differ."""
    if viewer_left_model == viewer_right_model:
        return viewer_left_model
    return f"{viewer_left_model}|{viewer_right_model}"


def _with_model(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``frame`` with a ``model`` column derived from the viewer models."""
    out = frame.copy()
    out["model"] = [
        _model_label(viewer_left_model=left, viewer_right_model=right)
        for left, right in zip(out["viewer_left_model"], out["viewer_right_model"])
    ]
    return out


def _model_performance_frame(run_level: pd.DataFrame) -> pd.DataFrame:
    """Per-model mean success / win / found fractions (one row per model)."""
    grouped = run_level.groupby("model", as_index=False).agg(
        round_success_fraction=("round_success_fraction", "mean"),
        wins_fraction=("wins_fraction", "mean"),
        mean_found_fraction=("mean_found_fraction", "mean"),
    )
    return grouped.sort_values(by="model").reset_index(drop=True)


def _characters_per_model_frame(run_level: pd.DataFrame) -> pd.DataFrame:
    """Per-model mean link characters used per round (one row per model)."""
    grouped = run_level.groupby("model", as_index=False).agg(
        mean_characters_used=("mean_characters_used", "mean"),
    )
    return grouped.sort_values(by="model").reset_index(drop=True)


def _round_by_round_frame(round_level: pd.DataFrame, models: list[str]) -> pd.DataFrame:
    """One row per round: per-model mean success, characters used, and perplexity.

    Columns are laid out as ``round_number``, then one ``success: <model>`` column
    per model, then ``chars: <model>``, then ``perplexity: <model>`` — so a chart
    reads a contiguous block of columns for each metric.
    """
    rounds = sorted(round_level["round_number"].unique())
    success = round_level.pivot_table(
        index="round_number", columns="model", values="success", aggfunc="mean"
    ).reindex(index=rounds, columns=models)
    characters = round_level.pivot_table(
        index="round_number", columns="model", values="characters_used", aggfunc="mean"
    ).reindex(index=rounds, columns=models)
    perplexity = round_level.pivot_table(
        index="round_number", columns="model", values="perplexity", aggfunc="mean"
    ).reindex(index=rounds, columns=models)
    frame = pd.DataFrame({"round_number": rounds})
    for model in models:
        frame[f"success: {model}"] = success[model].to_numpy()
    for model in models:
        frame[f"chars: {model}"] = characters[model].to_numpy()
    for model in models:
        frame[f"perplexity: {model}"] = perplexity[model].to_numpy()
    return frame


def _perplexity_vs_success_frame(run_level: pd.DataFrame, models: list[str]) -> pd.DataFrame:
    """One row per (run, team): perplexity plus round-success in the row's model column.

    The success value lands only in the ``success: <model>`` column matching the
    row's model (other model columns blank), so a scatter can draw one series per
    model sharing the single perplexity domain.
    """
    frame = pd.DataFrame({"perplexity": run_level["perplexity"].to_numpy()})
    for model in models:
        column: list[float | None] = []
        for row_model, success in zip(run_level["model"], run_level["round_success_fraction"]):
            if row_model == model:
                column.append(float(success))
            else:
                column.append(None)
        frame[f"success: {model}"] = column
    return frame


def _perplexity_vs_wins_frame(run_level: pd.DataFrame, models: list[str]) -> pd.DataFrame:
    """One row per (run, team): perplexity plus win fraction in the row's model column.

    Mirrors :func:`_perplexity_vs_success_frame` but with the competitive
    ``wins_fraction`` on the y-axis, so a scatter shows whether a team's typical
    perplexity tracks how often it beats its opponent.
    """
    frame = pd.DataFrame({"perplexity": run_level["perplexity"].to_numpy()})
    for model in models:
        column: list[float | None] = []
        for row_model, wins in zip(run_level["model"], run_level["wins_fraction"]):
            if row_model == model:
                column.append(float(wins))
            else:
                column.append(None)
        frame[f"wins: {model}"] = column
    return frame


def _head_to_head_frame(round_level: pd.DataFrame) -> pd.DataFrame:
    """One row per decided round (exactly one winning team): winner vs loser metrics.

    Restricted to rounds with a single winner and at least one loser (ties and
    all-lose rounds are dropped), so each row pairs the winning and losing team
    from the same run, round, and scene pair — a within-round, same-model
    comparison of who won against how they communicated.
    """
    rows: list[dict[str, object]] = []
    for _, group in round_level.groupby(["run_id", "round_number"]):
        winners = group[group["won"] == 1]
        losers = group[group["won"] == 0]
        if len(winners) != 1 or losers.empty:
            continue
        winner = winners.iloc[0]
        loser = losers.iloc[0]
        rows.append(
            {
                "model": winner["model"],
                "winner_perplexity": winner["perplexity"],
                "loser_perplexity": loser["perplexity"],
                "winner_repetition": winner["language_repetition"],
                "loser_repetition": loser["language_repetition"],
            }
        )
    return pd.DataFrame(rows)


def _winner_loser_by_model_frame(head_to_head: pd.DataFrame) -> pd.DataFrame:
    """Per-model mean winner vs loser perplexity and repetition over decided rounds."""
    grouped = head_to_head.groupby("model", as_index=False).agg(
        winner_perplexity=("winner_perplexity", "mean"),
        loser_perplexity=("loser_perplexity", "mean"),
        winner_repetition=("winner_repetition", "mean"),
        loser_repetition=("loser_repetition", "mean"),
    )
    return grouped.sort_values(by="model").reset_index(drop=True)


def _winner_loser_scatter_frame(head_to_head: pd.DataFrame) -> pd.DataFrame:
    """One row per decided round: winner perplexity (x) vs loser perplexity (y).

    Points below the ``y = x`` diagonal are rounds the lower-perplexity team won.
    """
    frame = head_to_head[["winner_perplexity", "loser_perplexity"]].dropna()
    return frame.reset_index(drop=True)


def _build_plot_specs(run_level: pd.DataFrame, round_level: pd.DataFrame) -> list[PlotSpec]:
    """Assemble every plot's helper table and chart specs from the exported frames."""
    run_level = _with_model(frame=run_level)
    round_level = _with_model(frame=round_level)
    models = sorted(run_level["model"].unique())

    model_perf = _model_performance_frame(run_level=run_level)
    chars = _characters_per_model_frame(run_level=run_level)
    round_by_round = _round_by_round_frame(round_level=round_level, models=models)
    perplexity_success = _perplexity_vs_success_frame(run_level=run_level, models=models)
    perplexity_wins = _perplexity_vs_wins_frame(run_level=run_level, models=models)
    head_to_head = _head_to_head_frame(round_level=round_level)
    winner_loser_by_model = _winner_loser_by_model_frame(head_to_head=head_to_head)
    winner_loser_scatter = _winner_loser_scatter_frame(head_to_head=head_to_head)

    model_count = len(models)
    success_cols = tuple(range(1, 1 + model_count))
    chars_cols = tuple(range(1 + model_count, 1 + 2 * model_count))
    perplexity_cols = tuple(range(1 + 2 * model_count, 1 + 3 * model_count))
    scatter_series = tuple(range(1, 1 + model_count))

    return [
        PlotSpec(
            tab_title=f"{_PLOT_PREFIX}Model Performance",
            frame=model_perf,
            charts=(
                ChartSpec(
                    title="Round success / win / found rate by model",
                    chart_type="COLUMN",
                    domain_col=0,
                    series_cols=(1, 2, 3),
                    x_title="model",
                    y_title="fraction",
                ),
            ),
        ),
        PlotSpec(
            tab_title=f"{_PLOT_PREFIX}Round by Round",
            frame=round_by_round,
            charts=(
                ChartSpec(
                    title="Round by round success rate",
                    chart_type="LINE",
                    domain_col=0,
                    series_cols=success_cols,
                    x_title="round",
                    y_title="mean success",
                ),
                ChartSpec(
                    title="Round by round characters used",
                    chart_type="LINE",
                    domain_col=0,
                    series_cols=chars_cols,
                    x_title="round",
                    y_title="mean characters used",
                ),
                ChartSpec(
                    title="Round by round perplexity",
                    chart_type="LINE",
                    domain_col=0,
                    series_cols=perplexity_cols,
                    x_title="round",
                    y_title="mean perplexity (nats)",
                ),
            ),
        ),
        PlotSpec(
            tab_title=f"{_PLOT_PREFIX}Perplexity vs Success",
            frame=perplexity_success,
            charts=(
                ChartSpec(
                    title="Perplexity vs round success (per run-team)",
                    chart_type="SCATTER",
                    domain_col=0,
                    series_cols=scatter_series,
                    x_title="perplexity (nats)",
                    y_title="round success fraction",
                ),
            ),
        ),
        PlotSpec(
            tab_title=f"{_PLOT_PREFIX}Characters per Model",
            frame=chars,
            charts=(
                ChartSpec(
                    title="Mean characters used per round by model",
                    chart_type="COLUMN",
                    domain_col=0,
                    series_cols=(1,),
                    x_title="model",
                    y_title="mean characters used",
                ),
            ),
        ),
        PlotSpec(
            tab_title=f"{_PLOT_PREFIX}Perplexity vs Wins",
            frame=perplexity_wins,
            charts=(
                ChartSpec(
                    title="Perplexity vs win fraction (per run-team)",
                    chart_type="SCATTER",
                    domain_col=0,
                    series_cols=scatter_series,
                    x_title="perplexity (nats)",
                    y_title="win fraction",
                ),
            ),
        ),
        PlotSpec(
            tab_title=f"{_PLOT_PREFIX}Winner vs Loser by Model",
            frame=winner_loser_by_model,
            charts=(
                ChartSpec(
                    title="Winner vs loser perplexity by model",
                    chart_type="COLUMN",
                    domain_col=0,
                    series_cols=(1, 2),
                    x_title="model",
                    y_title="mean perplexity (nats)",
                ),
                ChartSpec(
                    title="Winner vs loser repetition by model",
                    chart_type="COLUMN",
                    domain_col=0,
                    series_cols=(3, 4),
                    x_title="model",
                    y_title="mean repetition factor",
                ),
            ),
        ),
        PlotSpec(
            tab_title=f"{_PLOT_PREFIX}Winner vs Loser Perplexity",
            frame=winner_loser_scatter,
            charts=(
                ChartSpec(
                    title="Winner perplexity vs loser perplexity (per decided round)",
                    chart_type="SCATTER",
                    domain_col=0,
                    series_cols=(1,),
                    x_title="winner perplexity (nats)",
                    y_title="loser perplexity (nats)",
                ),
            ),
        ),
    ]


def _delete_plot_tabs(spreadsheet: gspread.Spreadsheet) -> None:
    """Delete every existing ``Plot: *`` tab so the rebuild starts clean."""
    for worksheet in spreadsheet.worksheets():
        if worksheet.title.startswith(_PLOT_PREFIX):
            logger.info("deleting existing tab %r", worksheet.title)
            spreadsheet.del_worksheet(worksheet)


def _source_range(sheet_id: int, row_count: int, column: int) -> dict[str, object]:
    """Return a Sheets API source range for one column (header row included)."""
    return {
        "sources": [
            {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": row_count + 1,
                "startColumnIndex": column,
                "endColumnIndex": column + 1,
            }
        ]
    }


def _add_chart_request(
    sheet_id: int, row_count: int, column_count: int, chart_index: int, chart: ChartSpec
) -> dict[str, object]:
    """Build one Sheets API ``addChart`` request anchored to the right of the helper table."""
    domain = {"domain": {"sourceRange": _source_range(sheet_id, row_count, chart.domain_col)}}
    series = [
        {
            "series": {"sourceRange": _source_range(sheet_id, row_count, column)},
            "targetAxis": "LEFT_AXIS",
        }
        for column in chart.series_cols
    ]
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": chart.title,
                    "basicChart": {
                        "chartType": chart.chart_type,
                        "legendPosition": "BOTTOM_LEGEND",
                        "headerCount": 1,
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": chart.x_title},
                            {"position": "LEFT_AXIS", "title": chart.y_title},
                        ],
                        "domains": [domain],
                        "series": series,
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": chart_index * _CHART_ROW_STRIDE,
                            "columnIndex": column_count + 1,
                        },
                        "widthPixels": _CHART_WIDTH_PX,
                        "heightPixels": _CHART_HEIGHT_PX,
                    }
                },
            }
        }
    }


def _write_plot_tab(spreadsheet: gspread.Spreadsheet, plot: PlotSpec) -> list[dict[str, object]]:
    """Create the plot's tab, write its helper table, and return its addChart requests.

    The grid is sized to fit both the helper table and the vertically stacked chart
    anchors (the Sheets API rejects an ``anchorCell`` past the last grid row).
    """
    rows_for_charts = len(plot.charts) * _CHART_ROW_STRIDE + 2
    worksheet = spreadsheet.add_worksheet(
        title=plot.tab_title,
        rows=max(len(plot.frame) + 2, rows_for_charts),
        cols=len(plot.frame.columns) + 10,
    )
    set_with_dataframe(
        worksheet=worksheet,
        dataframe=plot.frame,
        include_index=False,
        include_column_header=True,
        resize=False,
        string_escaping="default",
    )
    logger.info(
        "wrote %r: %d rows x %d cols, %d chart(s)",
        plot.tab_title,
        len(plot.frame),
        len(plot.frame.columns),
        len(plot.charts),
    )
    return [
        _add_chart_request(
            sheet_id=worksheet.id,
            row_count=len(plot.frame),
            column_count=len(plot.frame.columns),
            chart_index=index,
            chart=chart,
        )
        for index, chart in enumerate(plot.charts)
    ]


def _read_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the ``run_level`` and ``round_level`` frames from the exported workbook."""
    if not _XLSX.exists():
        raise FileNotFoundError(f"Workbook {_XLSX} not found — run the spot exporter first.")
    sheets = pd.read_excel(_XLSX, sheet_name=["run_level", "round_level"])
    return sheets["run_level"], sheets["round_level"]


def _parse_args() -> argparse.Namespace:
    """Parse CLI flags."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--credentials",
        type=Path,
        default=default_credentials_path(),
        help=f"Service-account key JSON (default ${CREDENTIALS_ENV} or ~/.config/glossogen).",
    )
    return parser.parse_args()


def main() -> None:
    """Rebuild every ``Plot: *`` tab and its embedded charts in the spot spreadsheet."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _parse_args()
    run_level, round_level = _read_frames()
    plots = _build_plot_specs(run_level=run_level, round_level=round_level)

    client = build_sheets_client(credentials_path=args.credentials)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    logger.info("opened %r", spreadsheet.title)

    _delete_plot_tabs(spreadsheet=spreadsheet)
    requests: list[dict[str, object]] = []
    for plot in plots:
        requests.extend(_write_plot_tab(spreadsheet=spreadsheet, plot=plot))
    spreadsheet.batch_update({"requests": requests})
    logger.info("added %d chart(s) across %d plot tab(s).", len(requests), len(plots))


if __name__ == "__main__":
    main()
