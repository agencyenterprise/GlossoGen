"use client";

/**
 * One analysis result, drawn as bars, lines, or a scatter.
 *
 * A group the query could not compute leaves a gap: bars draw nothing and lines
 * break, because `connectNulls` would invent a segment between two observations that
 * has no data behind it. That is the same claim the empty CSV cell makes, carried
 * into the picture.
 *
 * Marks are capped rather than filled to the band, lines are 2px, and dots clear the
 * 8px a pointer needs. The grid is a hairline in the border token so it stays behind
 * the data.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  ErrorBar,
  LabelList,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { components } from "@/types/api.gen";
import type { ChartRow } from "../chart-series";
import { ERROR_FIELD_PREFIX, buildChartData, buildScatterData } from "../chart-series";
import { SCATTER_SERIES_LIMIT } from "../series-palette";
import {
  AXIS_TICK,
  ChartLegend,
  EmptyChart,
  GRID_STROKE,
  SeriesTooltip,
  TooltipRow,
  TooltipShell,
  formatValue,
} from "./chart-chrome";

type AnalysisResult = components["schemas"]["AnalysisResult"];

const CHART_HEIGHT = 320;

const BAR_MAX_THICKNESS = 24;

/**
 * Above this many bars, a number on every cap stops being a label and becomes noise.
 * Below it, and with only one series, the caps are where the values read best and the
 * chart no longer depends on the eye to measure a bar against a gridline.
 */
const DIRECT_LABEL_LIMIT = 12;

/**
 * Past this label length, upright category labels collide and Recharts drops every
 * other one. The keyed grain makes that the normal case rather than the exception:
 * its categories are ontology ids and probe question ids, not budgets and model
 * names. Bars laid out horizontally give each label a whole row, which is the form
 * a sorted ranking wants anyway.
 */
const LONG_LABEL_CHARS = 14;

const HORIZONTAL_BAR_LIMIT = 30;

function wantsHorizontalBars(rows: ChartRow[]): boolean {
  if (rows.length > HORIZONTAL_BAR_LIMIT) {
    return false;
  }
  return rows.some(row => row.category.length > LONG_LABEL_CHARS);
}

function xAxisLabel(result: AnalysisResult): string {
  const key = result.group_by[0];
  if (key === undefined) {
    return "";
  }
  return key;
}

function AxisTitles({ x, y }: { x: string; y: string }) {
  return (
    <p className="mt-1 flex flex-wrap justify-between gap-2 text-[11px] text-muted-foreground">
      <span>{y === "" ? "" : `y: ${y}`}</span>
      <span>{x === "" ? "" : `x: ${x}`}</span>
    </p>
  );
}

/**
 * A metric's unit often ends in a parenthetical counted from one run
 * ("fraction of rounds succeeded (9/15)"). On an axis over many runs that trailing
 * count is a different run's arithmetic, so the unit is trimmed back to the part
 * that describes the quantity.
 */
function unitOf(scoreUnit: string): string {
  return scoreUnit.replace(/\s*\([^)]*\)\s*$/, "").trim();
}

function axisLabel(result: AnalysisResult, measureIndex: number): string {
  const measure = result.measures[measureIndex];
  if (measure === undefined) {
    return "";
  }
  const unit = unitOf(measure.score_unit);
  if (unit === "") {
    return `${measure.label} (${measure.aggregate})`;
  }
  return `${measure.label} (${measure.aggregate}, ${unit})`;
}

function HiddenSeriesNote({ count }: { count: number }) {
  if (count === 0) {
    return null;
  }
  return (
    <p className="mt-2 text-xs text-muted-foreground">
      {count} more series not drawn. Colours stop separating past eight, so narrow the selection or
      group on something coarser; every group is still in the table.
    </p>
  );
}

export function BarResultChart({
  result,
  measureIndex,
  errorMeasureIndex,
}: {
  result: AnalysisResult;
  measureIndex: number;
  errorMeasureIndex: number | null;
}) {
  const data = buildChartData(result, measureIndex, errorMeasureIndex);
  if (data.rows.length === 0) {
    return <EmptyChart message="This query produced no groups to draw." />;
  }
  const labelCaps = data.series.length === 1 && data.rows.length <= DIRECT_LABEL_LIMIT;
  const horizontal = wantsHorizontalBars(data.rows);
  const height = horizontal ? Math.max(CHART_HEIGHT, data.rows.length * 26 + 48) : CHART_HEIGHT;
  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={data.rows}
          layout={horizontal ? "vertical" : "horizontal"}
          margin={{ top: 8, right: 48, bottom: 4, left: 0 }}
        >
          <CartesianGrid stroke={GRID_STROKE} vertical={horizontal} horizontal={!horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" tick={AXIS_TICK} stroke={GRID_STROKE} />
              <YAxis
                type="category"
                dataKey="category"
                tick={AXIS_TICK}
                stroke={GRID_STROKE}
                width={264}
                interval={0}
              />
            </>
          ) : (
            <>
              <XAxis dataKey="category" tick={AXIS_TICK} stroke={GRID_STROKE} interval={0} />
              <YAxis tick={AXIS_TICK} stroke={GRID_STROKE} width={64} />
            </>
          )}
          <Tooltip
            cursor={{ fill: "var(--color-muted)", opacity: 0.4 }}
            content={props => <SeriesTooltip {...props} series={data.series} />}
          />
          {data.series.map(entry => (
            <Bar
              key={entry.key}
              dataKey={entry.key}
              name={entry.name}
              fill={entry.color}
              maxBarSize={BAR_MAX_THICKNESS}
              // The rounded end is the data end, so it follows the bar's direction.
              radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
            >
              {errorMeasureIndex === null ? null : (
                <ErrorBar
                  dataKey={`${ERROR_FIELD_PREFIX}${entry.key}`}
                  stroke={entry.color}
                  strokeWidth={1.5}
                  width={5}
                  direction={horizontal ? "x" : "y"}
                />
              )}
              {labelCaps ? (
                <LabelList
                  dataKey={entry.key}
                  position={horizontal ? "right" : "top"}
                  fill="var(--color-muted-foreground)"
                  fontSize={11}
                  formatter={(value: unknown) =>
                    typeof value === "number" ? formatValue(value) : ""
                  }
                />
              ) : null}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
      <AxisTitles x={xAxisLabel(result)} y={axisLabel(result, measureIndex)} />
      <ChartLegend series={data.series} />
      <HiddenSeriesNote count={data.hiddenSeriesCount} />
    </div>
  );
}

export function LineResultChart({
  result,
  measureIndex,
  errorMeasureIndex,
}: {
  result: AnalysisResult;
  measureIndex: number;
  errorMeasureIndex: number | null;
}) {
  const data = buildChartData(result, measureIndex, errorMeasureIndex);
  if (data.rows.length === 0) {
    return <EmptyChart message="This query produced no groups to draw." />;
  }
  return (
    <div>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={data.rows} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={GRID_STROKE} vertical={false} />
          <XAxis dataKey="category" tick={AXIS_TICK} stroke={GRID_STROKE} />
          <YAxis tick={AXIS_TICK} stroke={GRID_STROKE} width={64} />
          <Tooltip
            cursor={{ stroke: GRID_STROKE }}
            content={props => <SeriesTooltip {...props} series={data.series} />}
          />
          {data.series.map(entry => (
            <Line
              key={entry.key}
              // Straight segments, not a spline: a curve drawn between two
              // observations passes through values nothing measured, and with
              // sparse x values (three swap rounds, five budgets) it invents a
              // shape the data does not have.
              type="linear"
              dataKey={entry.key}
              name={entry.name}
              stroke={entry.color}
              strokeWidth={2}
              dot={{ r: 4, fill: entry.color, strokeWidth: 0 }}
              activeDot={{ r: 5 }}
              connectNulls={false}
            >
              {errorMeasureIndex === null ? null : (
                <ErrorBar
                  dataKey={`${ERROR_FIELD_PREFIX}${entry.key}`}
                  stroke={entry.color}
                  strokeWidth={1.5}
                  width={5}
                  direction="y"
                />
              )}
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
      <AxisTitles x={xAxisLabel(result)} y={axisLabel(result, measureIndex)} />
      <ChartLegend series={data.series} />
      <HiddenSeriesNote count={data.hiddenSeriesCount} />
    </div>
  );
}

export function ScatterResultChart({
  result,
  xMeasureIndex,
  yMeasureIndex,
}: {
  result: AnalysisResult;
  xMeasureIndex: number;
  yMeasureIndex: number;
}) {
  if (result.measures.length < 2) {
    return <EmptyChart message="A scatter needs two measures: one for each axis." />;
  }
  const scatter = buildScatterData(result, xMeasureIndex, yMeasureIndex);
  const series = scatter.series;
  const points = series.reduce((total, entry) => total + entry.points.length, 0);
  if (points === 0) {
    return (
      <EmptyChart message="No group has a number for both measures, so there is nothing to place." />
    );
  }
  const legend = series.map(entry => ({ key: entry.name, name: entry.name, color: entry.color }));
  return (
    <div>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 16, left: 0 }}>
          <CartesianGrid stroke={GRID_STROKE} />
          <XAxis
            type="number"
            dataKey="x"
            name={axisLabel(result, xMeasureIndex)}
            tick={AXIS_TICK}
            stroke={GRID_STROKE}
          />
          <YAxis
            type="number"
            dataKey="y"
            name={axisLabel(result, yMeasureIndex)}
            tick={AXIS_TICK}
            stroke={GRID_STROKE}
            width={64}
          />
          <ZAxis range={[64, 64]} />
          <Tooltip
            cursor={{ stroke: GRID_STROKE }}
            content={props => {
              const point = props.payload?.[0]?.payload;
              if (point === undefined) {
                return null;
              }
              return (
                <TooltipShell title={String(point.label)}>
                  <TooltipRow
                    color="var(--color-muted-foreground)"
                    label={axisLabel(result, xMeasureIndex)}
                    value={point.x}
                    observations={null}
                  />
                  <TooltipRow
                    color="var(--color-muted-foreground)"
                    label={axisLabel(result, yMeasureIndex)}
                    value={point.y}
                    observations={point.observations}
                  />
                </TooltipShell>
              );
            }}
          />
          {series.map(entry => (
            <Scatter key={entry.name} name={entry.name} data={entry.points} fill={entry.color} />
          ))}
        </ScatterChart>
      </ResponsiveContainer>
      <AxisTitles x={axisLabel(result, xMeasureIndex)} y={axisLabel(result, yMeasureIndex)} />
      <ChartLegend series={legend} />
      <HiddenSeriesNote count={scatter.hiddenSeriesCount} />
      {series.length > SCATTER_SERIES_LIMIT ? (
        <p className="mt-2 text-xs text-muted-foreground">
          Past {SCATTER_SERIES_LIMIT} series, scattered marks stop being reliably distinguishable by
          colour alone. Read the exact values from the table.
        </p>
      ) : null}
      <p className="mt-2 text-xs text-muted-foreground">
        One mark per group. A group missing either measure is not placed, since it has no position
        on that axis; {formatValue(points)} of {result.rows.length} are drawn.
      </p>
    </div>
  );
}
