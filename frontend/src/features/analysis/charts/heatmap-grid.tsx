"use client";

/**
 * A grid of one measure across two grouping keys.
 *
 * The colour is a single hue, light to dark on the light surface and dark to light on
 * the dark one, so magnitude reads as depth rather than as a change of hue. A cell the
 * query could not compute is drawn as the surface with a dashed outline: an empty cell
 * is not the ramp's lowest step, which would read as a measured zero.
 *
 * Written as a table rather than as SVG, so the values are selectable, the row and
 * column headers are announced, and the whole thing scrolls sideways when the grid is
 * wider than the card.
 */

import type { components } from "@/types/api.gen";
import { buildHeatmapData } from "../chart-series";
import { rampStep } from "../series-palette";
import { EmptyChart, formatValue } from "./chart-chrome";

type AnalysisResult = components["schemas"]["AnalysisResult"];

export function HeatmapGrid({
  result,
  measureIndex,
}: {
  result: AnalysisResult;
  measureIndex: number;
}) {
  if (result.group_by.length < 2) {
    return <EmptyChart message="A heatmap needs two grouping keys: one per axis." />;
  }
  const data = buildHeatmapData(result, measureIndex);
  if (data.cells.length === 0) {
    return <EmptyChart message="This query produced no groups to draw." />;
  }

  const byKey = new Map(data.cells.map(cell => [`${cell.column}|${cell.row}`, cell]));
  const measure = result.measures[measureIndex];

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-0.5 text-xs">
          <thead>
            <tr>
              <th className="px-2 py-1 text-left font-medium text-muted-foreground">
                {result.group_by[1]}
              </th>
              {data.columns.map(column => (
                <th
                  key={column}
                  className="px-2 py-1 text-center font-medium text-muted-foreground"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map(row => (
              <tr key={row}>
                <th className="px-2 py-1 text-left font-medium text-muted-foreground">
                  {row === "" ? "(empty)" : row}
                </th>
                {data.columns.map(column => {
                  const cell = byKey.get(`${column}|${row}`);
                  const value = cell?.value ?? null;
                  if (value === null) {
                    return (
                      <td
                        key={column}
                        title="no observations"
                        className="min-w-20 rounded-sm border border-dashed border-border px-2 py-2 text-center text-muted-foreground"
                      >
                        &ndash;
                      </td>
                    );
                  }
                  const step = rampStep(value, data.minimum, data.maximum);
                  return (
                    <td
                      key={column}
                      title={`${formatValue(value)} over ${cell?.observations ?? 0} observations`}
                      className="min-w-20 rounded-sm px-2 py-2 text-center tabular-nums"
                      style={{ backgroundColor: step.background, color: step.color }}
                    >
                      {formatValue(value)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        {measure === undefined ? "" : `${measure.label} (${measure.aggregate})`}, from{" "}
        {formatValue(data.minimum)} to {formatValue(data.maximum)}. Columns are {result.group_by[0]}
        , rows are {result.group_by[1]}. A dashed cell had no observations.
      </p>
    </div>
  );
}
