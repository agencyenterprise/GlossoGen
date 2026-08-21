"use client";

/**
 * One chart on a dashboard: its query, its picture, and the numbers behind it.
 *
 * The dashboard's filters are merged onto the chart's own before the query runs, so a
 * chart saved months ago follows the cohort the dashboard now points at.
 *
 * The table is always one click away, which is also what allows the lighter series
 * colours: they sit under 3:1 against the light surface, and using them at all
 * requires the values to stay readable some other way.
 */

import { useState } from "react";
import { Download, Loader2, Pencil, Table2, Trash2 } from "lucide-react";
import { cn } from "@/shared/lib/cn";
import { downloadResultCsv } from "./chart-csv-download";
import { isCompleteFilter } from "./dimension-filter-builder";
import { ChartBuilderPanel } from "./chart-builder-panel";
import { BarResultChart, LineResultChart, ScatterResultChart } from "./charts/analysis-chart";
import { EmptyChart } from "./charts/chart-chrome";
import { isNarrowedSelection } from "./selection-scope";
import { HeatmapGrid } from "./charts/heatmap-grid";
import { ResultTable } from "./charts/result-table";
import type { AnalysisResult, DimensionFilter, RunSelection } from "./use-analysis-data";
import { useAnalysisFields, useAnalysisQuery } from "./use-analysis-data";
import type { ChartSpec } from "./use-dashboards";

function ChartBody({
  chart,
  result,
  showTable,
}: {
  chart: ChartSpec;
  result: AnalysisResult;
  showTable: boolean;
}) {
  if (showTable || chart.kind === "table") {
    return <ResultTable result={result} />;
  }
  if (chart.kind === "heatmap") {
    return <HeatmapGrid result={result} measureIndex={chart.encoding.measure_index} />;
  }
  if (chart.kind === "scatter") {
    return (
      <ScatterResultChart
        result={result}
        xMeasureIndex={chart.encoding.measure_index}
        yMeasureIndex={chart.encoding.y_measure_index}
      />
    );
  }
  if (chart.kind === "line") {
    return (
      <LineResultChart
        result={result}
        measureIndex={chart.encoding.measure_index}
        errorMeasureIndex={chart.encoding.error_measure_index ?? null}
      />
    );
  }
  return (
    <BarResultChart
      result={result}
      measureIndex={chart.encoding.measure_index}
      errorMeasureIndex={chart.encoding.error_measure_index ?? null}
    />
  );
}

export function ChartCard({
  chart,
  selection,
  dashboardFilters,
  onChange,
  onRemove,
}: {
  chart: ChartSpec;
  selection: RunSelection;
  dashboardFilters: DimensionFilter[];
  onChange: (chart: ChartSpec) => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [showTable, setShowTable] = useState(false);

  const scoped = isNarrowedSelection(selection);

  // Fetched per chart, because what a selection can be grouped and measured by
  // depends on the grain, and two charts on one dashboard can read different ones.
  // React Query holds one copy per (selection, grain) however many charts ask.
  const fields = useAnalysisFields({
    selection,
    grain: chart.query.grain,
    enabled: editing && scoped,
  });

  const query = {
    ...chart.query,
    filters: [...dashboardFilters, ...chart.query.filters].filter(isCompleteFilter),
  };
  const answer = useAnalysisQuery({ selection, query, enabled: scoped });

  return (
    <section className="rounded-lg border border-border p-4">
      <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">{chart.title}</h3>
          {answer.data === undefined ? null : (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {answer.data.rows.length} groups over {answer.data.run_count} runs and{" "}
              {answer.data.observation_count} {answer.data.grain} observations
              {answer.data.truncated ? " (clipped by the row limit)" : ""}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Show the numbers"
            aria-pressed={showTable}
            onClick={() => setShowTable(value => !value)}
            className={cn(
              "rounded-md border border-border p-1.5 text-muted-foreground hover:bg-muted",
              showTable ? "bg-muted text-foreground" : ""
            )}
          >
            <Table2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Download these rows"
            disabled={answer.data === undefined}
            onClick={() => {
              if (answer.data !== undefined) {
                downloadResultCsv(answer.data, chart.title);
              }
            }}
            className="rounded-md border border-border p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-40"
          >
            <Download className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Edit this chart"
            aria-pressed={editing}
            onClick={() => setEditing(value => !value)}
            className={cn(
              "rounded-md border border-border p-1.5 text-muted-foreground hover:bg-muted",
              editing ? "bg-muted text-foreground" : ""
            )}
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Remove this chart"
            onClick={onRemove}
            className="rounded-md border border-border p-1.5 text-muted-foreground hover:bg-muted"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {editing ? (
        <div className="mb-4 rounded-md border border-dashed border-border p-3">
          <ChartBuilderPanel
            chart={chart}
            catalog={fields.data}
            onChange={onChange}
            onGrainChange={grain =>
              onChange({ ...chart, query: { ...chart.query, grain, group_by: [] } })
            }
          />
        </div>
      ) : null}

      {scoped ? null : (
        <EmptyChart message="Pick a scenario or a label above, and this chart will draw." />
      )}

      {scoped && answer.isPending ? (
        <div className="flex h-64 items-center justify-center text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
        </div>
      ) : null}

      {answer.error !== null ? <EmptyChart message={answer.error.message} /> : null}

      {answer.data === undefined ? null : (
        <>
          <ChartBody chart={chart} result={answer.data} showTable={showTable} />
          {answer.data.missing_run_ids.length > 0 ? (
            <p className="mt-2 text-xs text-muted-foreground">
              {answer.data.missing_run_ids.length} runs this dashboard names no longer exist, so
              they are not in these numbers.
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
