import { describe, expect, it } from "vitest";
import { buildChartData, buildScatterData } from "./chart-series";
import { SERIES_SLOT_COUNT } from "./series-palette";
import type { AnalysisResult } from "./use-analysis-data";

/**
 * Reshaping one result into the rows a chart draws.
 *
 * The claim under the most pressure is the one the module docstring makes: series past
 * the last colour slot are reported, never merged. It was structurally impossible to
 * report, because the count compared a list against a map over that same list.
 */

function measure(index: number) {
  return {
    column_key: `metric.m${index}:mean`,
    label: `M${index}`,
    score_unit: "",
    aggregate: "mean",
  };
}

function result(measureCount: number, groupBy: string[], rows: AnalysisResult["rows"]) {
  return {
    grain: "run" as const,
    group_by: groupBy,
    measures: Array.from({ length: measureCount }, (_, index) => measure(index)),
    rows,
    run_count: rows.length,
    observation_count: rows.length,
    truncated: false,
    missing_run_ids: [],
  };
}

function cells(values: Array<number | null>) {
  return values.map(value => ({
    value,
    observation_count: value === null ? 0 : 1,
    missing_count: value === null ? 1 : 0,
  }));
}

describe("buildChartData with measures as the series", () => {
  it("reports the measures it could not colour", () => {
    const measureCount = SERIES_SLOT_COUNT + 3;
    const answer = result(
      measureCount,
      ["model_class"],
      [{ group_values: ["closed"], run_count: 1, cells: cells(Array(measureCount).fill(0.5)) }]
    );

    const data = buildChartData(answer, 0, null);

    expect(data.series).toHaveLength(SERIES_SLOT_COUNT);
    expect(data.hiddenSeriesCount).toBe(3);
  });

  it("reports nothing hidden when every measure fits", () => {
    const answer = result(
      2,
      ["model_class"],
      [{ group_values: ["closed"], run_count: 1, cells: cells([0.5, 0.25]) }]
    );

    expect(buildChartData(answer, 0, null).hiddenSeriesCount).toBe(0);
  });

  it("does not draw the error measure as a series of its own", () => {
    const answer = result(
      2,
      ["model_class"],
      [{ group_values: ["closed"], run_count: 1, cells: cells([0.5, 0.05]) }]
    );

    const data = buildChartData(answer, 0, 1);

    expect(data.series).toHaveLength(1);
    expect(data.hiddenSeriesCount).toBe(0);
  });

  it("carries a missing value through as null rather than zero", () => {
    const answer = result(
      1,
      ["model_class"],
      [{ group_values: ["open"], run_count: 1, cells: cells([null]) }]
    );

    const data = buildChartData(answer, 0, null);

    const first = data.rows[0];
    const series = data.series[0];
    if (first === undefined || series === undefined) {
      throw new Error("expected one row and one series");
    }
    expect(first[series.key]).toBeNull();
  });
});

describe("buildScatterData", () => {
  it("reports the series it could not colour", () => {
    const rows = Array.from({ length: SERIES_SLOT_COUNT + 2 }, (_, index) => ({
      group_values: [`run-${index}`, `series-${index}`],
      run_count: 1,
      cells: cells([0.5, 0.25]),
    }));

    const scatter = buildScatterData(result(2, ["run_id", "series"], rows), 0, 1);

    expect(scatter.series).toHaveLength(SERIES_SLOT_COUNT);
    expect(scatter.hiddenSeriesCount).toBe(2);
  });

  it("leaves out a group missing either axis, since it has no position", () => {
    const rows = [
      { group_values: ["a", "s"], run_count: 1, cells: cells([0.5, 0.25]) },
      { group_values: ["b", "s"], run_count: 1, cells: cells([0.5, null]) },
    ];

    const scatter = buildScatterData(result(2, ["run_id", "series"], rows), 0, 1);

    const series = scatter.series[0];
    if (series === undefined) {
      throw new Error("expected one series");
    }
    expect(series.points).toHaveLength(1);
  });
});
