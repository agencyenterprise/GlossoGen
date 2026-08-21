/**
 * The rows behind a chart, as a CSV file.
 *
 * Written from the same result the chart drew, so the file and the picture cannot
 * disagree. Each measure spends three columns: the aggregate, how many observations
 * it covered, and how many were missing. A value that could not be computed is an
 * empty cell, never a zero, which is the rule the whole export rests on.
 */

import { UNGROUPED_LABEL } from "./chart-series";
import type { AnalysisResult } from "./use-analysis-data";

/**
 * Render one cell the way the server's CSV writer does.
 *
 * Group values are labels, knob values and agent ids, which come from the same data
 * the server sanitizes, so the two files have to treat them identically. The rules are
 * `csv_cell_text.py`'s: newlines become single spaces, control characters are stripped
 * except tab, which is a legal cell character that quoting handles, and a cell opening
 * with `=`, `+`, `@` or a tab is prefixed with an apostrophe so a spreadsheet reads it
 * as text. Without that guard a judge note beginning `@B means ...` renders as
 * `#NAME?` and the value is lost.
 *
 * `-` is deliberately not a formula leader on either side: negative numbers open with
 * it, and quoting all of them would cost more than the risk.
 */
const NEWLINES = /\r\n|\r|\n/g;

// C0 minus tab, plus DEL and C1 - the same set the server strips.
const CONTROL_CHARS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/g;

const FORMULA_LEADERS = ["=", "+", "@", "\t"];

function sanitizeCell(text: string): string {
  const flattened = text.replace(NEWLINES, " ").replace(CONTROL_CHARS, "");
  if (FORMULA_LEADERS.some(leader => flattened.startsWith(leader))) {
    return `'${flattened}`;
  }
  return flattened;
}

function escapeCell(text: string): string {
  const cell = sanitizeCell(text);
  if (/[",]/.test(cell)) {
    return `"${cell.replace(/"/g, '""')}"`;
  }
  return cell;
}

/** Render one result as CSV text. */
export function resultToCsv(result: AnalysisResult): string {
  const groupHeaders = result.group_by.length === 0 ? ["group"] : result.group_by;
  const header = [...groupHeaders, "runs"];
  for (const measure of result.measures) {
    header.push(
      measure.column_key,
      `${measure.column_key}:observations`,
      `${measure.column_key}:missing`
    );
  }

  const lines = [header.map(escapeCell).join(",")];
  for (const row of result.rows) {
    const cells = groupHeaders.map((_, index) => row.group_values[index] ?? UNGROUPED_LABEL);
    cells.push(String(row.run_count));
    for (const cell of row.cells) {
      cells.push(
        cell.value === null ? "" : String(cell.value),
        String(cell.observation_count),
        String(cell.missing_count)
      );
    }
    lines.push(cells.map(escapeCell).join(","));
  }
  return `${lines.join("\n")}\n`;
}

/** Hand the browser a CSV of the chart's rows. */
export function downloadResultCsv(result: AnalysisResult, title: string): void {
  const blob = new Blob([resultToCsv(result)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${title.replace(/[^a-z0-9]+/gi, "_").toLowerCase() || "analysis"}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
