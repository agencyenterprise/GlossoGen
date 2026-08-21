import { describe, expect, it } from "vitest";
import { resultToCsv } from "./chart-csv-download";
import type { AnalysisResult } from "./use-analysis-data";

/**
 * The rows behind a chart, as the server's CSV writer would render them.
 *
 * The cell rules are `csv_cell_text.py`'s, and the reason they have to match is that
 * both files carry the same data: labels, knob values, agent ids and judge prose.
 */

/** One line of a rendered CSV, failing the test rather than the type checker. */
function lineOf(csv: string, index: number): string {
  const line = csv.split("\n")[index];
  if (line === undefined) {
    throw new Error(`the CSV has no line ${index}`);
  }
  return line;
}

function result(patch: Partial<AnalysisResult>): AnalysisResult {
  return {
    grain: "run",
    group_by: ["model_class"],
    measures: [
      {
        column_key: "metric.round_success:mean",
        label: "Round success",
        score_unit: "",
        aggregate: "mean",
      },
    ],
    rows: [],
    run_count: 0,
    observation_count: 0,
    truncated: false,
    missing_run_ids: [],
    ...patch,
  };
}

function row(groupValues: string[], value: number | null) {
  return {
    group_values: groupValues,
    run_count: 1,
    cells: [
      {
        value,
        observation_count: value === null ? 0 : 1,
        missing_count: value === null ? 1 : 0,
      },
    ],
  };
}

const TAB = "\u0009";
const BELL = "\u0007";

describe("resultToCsv", () => {
  it("writes a measure as its aggregate, its observations and what was missing", () => {
    const csv = resultToCsv(result({ rows: [row(["closed"], 0.5)] }));

    expect(lineOf(csv, 0)).toBe(
      "model_class,runs,metric.round_success:mean," +
        "metric.round_success:mean:observations,metric.round_success:mean:missing"
    );
    expect(lineOf(csv, 1)).toBe("closed,1,0.5,1,0");
  });

  it("leaves a cell empty when nothing could be computed", () => {
    // Never a zero: the whole export rests on those being different claims.
    const csv = resultToCsv(result({ rows: [row(["open"], null)] }));

    expect(lineOf(csv, 1)).toBe("open,1,,0,1");
  });

  it("names the ungrouped row the way the chart and the table do", () => {
    const csv = resultToCsv(result({ group_by: [], rows: [row([], 0.5)] }));

    expect(lineOf(csv, 1).startsWith("All runs,")).toBe(true);
  });

  it("guards a cell a spreadsheet would read as a formula", () => {
    const csv = resultToCsv(result({ rows: [row(["@B means north"], 0.5)] }));

    expect(lineOf(csv, 1).startsWith("'@B means north,")).toBe(true);
  });

  it("flattens a newline to a space", () => {
    const csv = resultToCsv(result({ rows: [row(["two\nlines"], 0.5)] }));

    expect(lineOf(csv, 1)).toBe("two lines,1,0.5,1,0");
  });

  it("strips a control character but keeps tab", () => {
    // Unquoted, because a tab is not the delimiter: Python's `csv` writer leaves it
    // unquoted too, which is what makes the two files identical.
    const csv = resultToCsv(result({ rows: [row(["a" + BELL + "b" + TAB + "c"], 0.5)] }));

    expect(lineOf(csv, 1)).toBe("ab" + TAB + "c,1,0.5,1,0");
  });

  it("quotes a cell holding a comma or a quote", () => {
    const csv = resultToCsv(result({ rows: [row(['a,b "c"'], 0.5)] }));

    expect(lineOf(csv, 1)).toBe('"a,b ""c""",1,0.5,1,0');
  });
});
