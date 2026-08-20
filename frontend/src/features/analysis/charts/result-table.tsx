"use client";

/**
 * The numbers behind a chart, as a table.
 *
 * Always reachable from every chart, which is what lets the lighter series colours be
 * used at all: a reader who cannot separate two hues can read the values here. It also
 * carries what a mark cannot: how many observations each aggregate covered, and how
 * many were missing.
 */

import type { components } from "@/types/api.gen";
import { UNGROUPED_LABEL } from "../chart-series";
import { formatValue } from "./chart-chrome";

type AnalysisResult = components["schemas"]["AnalysisResult"];

export function ResultTable({ result }: { result: AnalysisResult }) {
  const groupHeaders = result.group_by.length === 0 ? ["group"] : result.group_by;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            {groupHeaders.map(header => (
              <th key={header} className="px-2 py-1.5 font-medium">
                {header}
              </th>
            ))}
            <th className="px-2 py-1.5 font-medium">runs</th>
            {result.measures.map(measure => (
              <th key={measure.column_key} className="px-2 py-1.5 text-right font-medium">
                {measure.label} ({measure.aggregate})
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, index) => (
            <tr
              key={`${row.group_values.join("|")}-${index}`}
              className="border-b border-border/50"
            >
              {groupHeaders.map((header, position) => (
                <td key={header} className="px-2 py-1.5">
                  {row.group_values[position] ?? UNGROUPED_LABEL}
                </td>
              ))}
              <td className="px-2 py-1.5 tabular-nums">{row.run_count}</td>
              {row.cells.map((cell, position) => (
                <td key={position} className="px-2 py-1.5 text-right tabular-nums">
                  <span className={cell.value === null ? "text-muted-foreground" : ""}>
                    {cell.value === null ? "—" : formatValue(cell.value)}
                  </span>
                  <span className="ml-2 text-[11px] text-muted-foreground">
                    n={cell.observation_count}
                    {cell.missing_count > 0 ? ` · ${cell.missing_count} missing` : ""}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
