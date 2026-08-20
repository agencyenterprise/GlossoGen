/**
 * The chart being edited, and what a new one starts as.
 *
 * A draft is the stored `ChartSpec` shape exactly, so saving a dashboard is a copy
 * rather than a translation, and opening one puts the builder back where it was.
 *
 * A new chart starts on the run grain with no grouping and one measure, which answers
 * "what is this cohort's average" before anything is chosen. Every field is then one
 * control away.
 */

import type { AnalysisMeasureField, AnalysisQuerySpec, MeasureSpec } from "./use-analysis-data";
import type { ChartEncoding, ChartKind, ChartSpec } from "./use-dashboards";

export const DEFAULT_RESULT_LIMIT = 200;

export const AGGREGATES = [
  "mean",
  "median",
  "sum",
  "count",
  "min",
  "max",
  "stddev",
  "sem",
] as const;

export const CHART_KINDS: ChartKind[] = ["bar", "line", "scatter", "heatmap", "table"];

/** How many grouping keys a chart form can read. */
export function requiredGroupKeys(kind: ChartKind): number {
  if (kind === "heatmap") {
    return 2;
  }
  return 0;
}

function firstMeasure(measures: AnalysisMeasureField[]): MeasureSpec {
  const preferred =
    measures.find(measure => measure.source === "metric" && measure.rows_with_value > 0) ??
    measures[0];
  if (preferred === undefined) {
    return { source: "run_column", key: "total_cost_usd", aggregate: "mean" };
  }
  return {
    source: preferred.source === "run_column" ? "run_column" : "metric",
    key: preferred.key,
    aggregate: "mean",
  };
}

/** Build the query a fresh chart starts with, given what the selection carries. */
export function newQuerySpec(measures: AnalysisMeasureField[]): AnalysisQuerySpec {
  return {
    grain: "run",
    filters: [],
    group_by: [],
    measures: [firstMeasure(measures)],
    sort: "group",
    sort_measure_index: 0,
    limit: DEFAULT_RESULT_LIMIT,
  };
}

/** Build a fresh chart. */
export function newChart(chartId: string, measures: AnalysisMeasureField[]): ChartSpec {
  return {
    chart_id: chartId,
    title: "Untitled chart",
    kind: "bar",
    query: newQuerySpec(measures),
    // Both axes on the only measure a fresh chart has. A scatter needs two and the
    // builder moves this when a second arrives; starting at 1 pointed past the list,
    // which the stored spec refuses, and the default kind is bar, which never reads
    // this, so the refusal only showed up on save.
    encoding: { measure_index: 0, y_measure_index: 0, error_measure_index: null },
  };
}

/**
 * Keep an encoding pointing at measures that exist, after the list changes.
 *
 * The error measure is carried through rather than dropped, and cleared only when it
 * can no longer be drawn: error bars are subtracted from the series, so they need a
 * second measure and cannot sit on the one they annotate. Rebuilding the object
 * without the field would silently discard a configured choice, since it is optional
 * in the stored spec and its absence type-checks.
 */
export function clampEncoding(encoding: ChartEncoding, measureCount: number): ChartEncoding {
  const last = Math.max(0, measureCount - 1);
  const measureIndex = Math.min(encoding.measure_index, last);
  const errorIndex =
    encoding.error_measure_index === null || encoding.error_measure_index === undefined
      ? null
      : Math.min(encoding.error_measure_index, last);
  const errorDrawable = errorIndex !== null && measureCount > 1 && errorIndex !== measureIndex;
  return {
    measure_index: measureIndex,
    y_measure_index: Math.min(encoding.y_measure_index, last),
    error_measure_index: errorDrawable ? errorIndex : null,
  };
}

/** A chart id that does not collide with the ones already on the dashboard. */
export function nextChartId(existing: ChartSpec[]): string {
  const used = new Set(existing.map(chart => chart.chart_id));
  let index = existing.length + 1;
  while (used.has(`chart-${index}`)) {
    index += 1;
  }
  return `chart-${index}`;
}
