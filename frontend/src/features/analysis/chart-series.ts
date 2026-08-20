/**
 * Turning one analysis result into the rows a chart draws.
 *
 * The server answers in long form: a row per group, a cell per measure. Recharts
 * wants a row per category with one field per series, so the reshaping happens here
 * and once, rather than inside each chart.
 *
 * Which key becomes the series depends on how many the query grouped by. With one
 * key the measures are the series, so several metrics sit side by side. With two,
 * the second key is the series and only the first measure is drawn: the alternative
 * is measures times series, which no legend can carry. The rest of the measures stay
 * in the table under the chart.
 *
 * Series past the last colour slot are reported, never merged. Merging them would
 * mean averaging aggregates that were computed over different numbers of runs, which
 * is a different number than the one the server answered with.
 */

import type { components } from "@/types/api.gen";
import { SERIES_SLOT_COUNT, seriesColor } from "./series-palette";

type AnalysisResult = components["schemas"]["AnalysisResult"];
type AnalysisResultRow = components["schemas"]["AnalysisResultRow"];

export interface ChartSeries {
  /** Field name this series occupies on every row. */
  key: string;
  name: string;
  color: string;
}

export interface ChartRow {
  category: string;
  [field: string]: string | number | null;
}

export interface ChartData {
  series: ChartSeries[];
  rows: ChartRow[];
  /** Series the palette could not carry, left undrawn rather than merged. */
  hiddenSeriesCount: number;
}

export interface ScatterPoint {
  x: number;
  y: number;
  label: string;
  observations: number;
}

export interface ScatterSeries {
  name: string;
  color: string;
  points: ScatterPoint[];
}

export interface ScatterData {
  series: ScatterSeries[];
  /** Series the palette could not carry, left undrawn rather than merged. */
  hiddenSeriesCount: number;
}

export interface HeatmapCell {
  column: string;
  row: string;
  value: number | null;
  observations: number;
}

export interface HeatmapData {
  columns: string[];
  rows: string[];
  cells: HeatmapCell[];
  minimum: number;
  maximum: number;
}

export const COUNT_FIELD_PREFIX = "n:";

export const ERROR_FIELD_PREFIX = "err:";

/**
 * What the single row of an ungrouped query is called.
 *
 * Exported because the CSV writes the same rows: the file and the chart naming that
 * row differently is the disagreement the download exists to rule out.
 */
export const UNGROUPED_LABEL = "All runs";

function categoryOf(row: AnalysisResultRow): string {
  const first = row.group_values[0];
  if (first === undefined || first === "") {
    return UNGROUPED_LABEL;
  }
  return first;
}

function distinct(values: string[]): string[] {
  return Array.from(new Set(values));
}

/**
 * Build the rows a bar or line chart draws.
 *
 * ``errorMeasureIndex`` names a measure drawn as error bars rather than as a series
 * of its own: a metric's standard error beside its mean. It is dropped from the
 * series list, since a spread is not a quantity to compare against the means.
 */
export function buildChartData(
  result: AnalysisResult,
  measureIndex: number,
  errorMeasureIndex: number | null
): ChartData {
  if (result.group_by.length < 2) {
    return chartDataByMeasure(result, measureIndex, errorMeasureIndex);
  }
  return chartDataBySeriesKey(result, measureIndex, errorMeasureIndex);
}

function chartDataByMeasure(
  result: AnalysisResult,
  measureIndex: number,
  errorMeasureIndex: number | null
): ChartData {
  const drawableIndexes = result.measures
    .map((_, index) => index)
    .filter(index => index !== errorMeasureIndex);
  const drawnIndexes = drawableIndexes.slice(0, SERIES_SLOT_COUNT);
  const series = drawnIndexes.map((measureRow, position) => ({
    key: result.measures[measureRow]?.column_key ?? String(measureRow),
    name: `${result.measures[measureRow]?.label} (${result.measures[measureRow]?.aggregate})`,
    color: seriesColor(position),
  }));

  const rows = result.rows.map(row => {
    const built: ChartRow = { category: categoryOf(row) };
    drawnIndexes.forEach((measureRow, position) => {
      const entry = series[position];
      if (entry === undefined) {
        return;
      }
      const cell = row.cells[measureRow];
      built[entry.key] = cell?.value ?? null;
      built[`${COUNT_FIELD_PREFIX}${entry.key}`] = cell?.observation_count ?? 0;
      if (errorMeasureIndex !== null && measureRow === measureIndex) {
        built[`${ERROR_FIELD_PREFIX}${entry.key}`] = row.cells[errorMeasureIndex]?.value ?? null;
      }
    });
    return built;
  });

  return {
    series,
    rows,
    // Against what was drawable, not against `series`: `series` is a map over
    // `drawnIndexes`, so the two are the same length by construction and the
    // difference was always zero.
    hiddenSeriesCount: drawableIndexes.length - drawnIndexes.length,
  };
}

function chartDataBySeriesKey(
  result: AnalysisResult,
  measureIndex: number,
  errorMeasureIndex: number | null
): ChartData {
  const seriesValues = distinct(result.rows.map(row => row.group_values[1] ?? ""));
  const drawn = seriesValues.slice(0, SERIES_SLOT_COUNT);
  const series = drawn.map((value, index) => ({
    key: value,
    name: value === "" ? "(empty)" : value,
    color: seriesColor(index),
  }));

  const byCategory = new Map<string, ChartRow>();
  for (const row of result.rows) {
    const category = categoryOf(row);
    const seriesValue = row.group_values[1] ?? "";
    if (!drawn.includes(seriesValue)) {
      continue;
    }
    const existing = byCategory.get(category) ?? { category };
    const cell = row.cells[measureIndex];
    existing[seriesValue] = cell?.value ?? null;
    existing[`${COUNT_FIELD_PREFIX}${seriesValue}`] = cell?.observation_count ?? 0;
    if (errorMeasureIndex !== null) {
      existing[`${ERROR_FIELD_PREFIX}${seriesValue}`] = row.cells[errorMeasureIndex]?.value ?? null;
    }
    byCategory.set(category, existing);
  }

  return {
    series,
    rows: Array.from(byCategory.values()),
    hiddenSeriesCount: seriesValues.length - drawn.length,
  };
}

/** Build the points a scatter draws: one per group, two measures as the axes. */
export function buildScatterData(
  result: AnalysisResult,
  xMeasureIndex: number,
  yMeasureIndex: number
): ScatterData {
  const grouped = new Map<string, ScatterPoint[]>();
  for (const row of result.rows) {
    const x = row.cells[xMeasureIndex]?.value;
    const y = row.cells[yMeasureIndex]?.value;
    if (x === null || x === undefined || y === null || y === undefined) {
      continue;
    }
    const seriesValue = row.group_values[1] ?? "";
    const points = grouped.get(seriesValue) ?? [];
    points.push({
      x,
      y,
      label: categoryOf(row),
      observations: row.cells[xMeasureIndex]?.observation_count ?? 0,
    });
    grouped.set(seriesValue, points);
  }

  const all = Array.from(grouped.entries());
  const drawn = all.slice(0, SERIES_SLOT_COUNT);
  return {
    series: drawn.map(([name, points], index) => ({
      name: name === "" ? "Runs" : name,
      color: seriesColor(index),
      points,
    })),
    hiddenSeriesCount: all.length - drawn.length,
  };
}

/** Build the grid a heatmap draws: the two group keys as axes, one measure as colour. */
export function buildHeatmapData(result: AnalysisResult, measureIndex: number): HeatmapData {
  const columns = distinct(result.rows.map(row => categoryOf(row)));
  const rows = distinct(result.rows.map(row => row.group_values[1] ?? ""));
  const cells: HeatmapCell[] = result.rows.map(row => ({
    column: categoryOf(row),
    row: row.group_values[1] ?? "",
    value: row.cells[measureIndex]?.value ?? null,
    observations: row.cells[measureIndex]?.observation_count ?? 0,
  }));

  const present = cells.map(cell => cell.value).filter((value): value is number => value !== null);

  return {
    columns,
    rows,
    cells,
    minimum: present.length === 0 ? 0 : Math.min(...present),
    maximum: present.length === 0 ? 0 : Math.max(...present),
  };
}
